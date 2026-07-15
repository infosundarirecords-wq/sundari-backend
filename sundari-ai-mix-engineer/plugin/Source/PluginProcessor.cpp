/*
  PluginProcessor.cpp
  =====================
*/

#include "PluginProcessor.h"
#include "PluginEditor.h"

namespace sundari
{

SundariAudioProcessor::SundariAudioProcessor()
    : AudioProcessor (BusesProperties()
                           .withInput  ("Input",  juce::AudioChannelSet::stereo(), true)
                           .withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "PARAMETERS", createParameterLayout())
{
    captureBuffer.setSize (2, 44100 * 10); // 10 second rolling capture buffer at init sample rate
}

SundariAudioProcessor::~SundariAudioProcessor() = default;

juce::AudioProcessorValueTreeState::ParameterLayout SundariAudioProcessor::createParameterLayout()
{
    std::vector<std::unique_ptr<juce::RangedAudioParameter>> params;

    // Bypass toggle — user chahe to AI processing ko poori tarah bypass
    // kar sakta hai, sirf plugin ko "transparent passthrough" mode mein
    // daal kar. Yeh AI-decided parameters se independent hai.
    params.push_back (std::make_unique<juce::AudioParameterBool> (
        juce::ParameterID { "bypass", 1 }, "Bypass", false));

    // Master output gain — user ka manual trim, AI decision ke upar
    params.push_back (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { "outputGain", 1 }, "Output Gain",
        juce::NormalisableRange<float> (-24.0f, 24.0f, 0.1f), 0.0f));

    return { params.begin(), params.end() };
}

void SundariAudioProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    currentSampleRate = sampleRate;

    juce::dsp::ProcessSpec spec;
    spec.sampleRate = sampleRate;
    spec.maximumBlockSize = (juce::uint32) samplesPerBlock;
    spec.numChannels = 2;

    for (auto& band : eqBands)
        band.prepare (spec);

    dynamics.prepare (spec);

    captureBuffer.setSize (2, (int) (sampleRate * 10), false, true, true);
    captureBuffer.clear();
    captureWritePos = 0;
}

void SundariAudioProcessor::releaseResources() {}

bool SundariAudioProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    return layouts.getMainInputChannelSet() == juce::AudioChannelSet::stereo()
        && layouts.getMainOutputChannelSet() == juce::AudioChannelSet::stereo();
}

void SundariAudioProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;

    auto* bypassParam = apvts.getRawParameterValue ("bypass");
    if (bypassParam != nullptr && bypassParam->load() > 0.5f)
        return; // Passthrough — koi processing nahi

    // --- Rolling capture buffer mein latest audio copy karna (analysis ke liye) ---
    // Yeh sirf ek memcpy jaisa cheap operation hai, audio thread ke liye safe.
    const int numSamples = buffer.getNumSamples();
    const int captureLength = captureBuffer.getNumSamples();
    for (int ch = 0; ch < juce::jmin (2, buffer.getNumChannels()); ++ch)
    {
        for (int i = 0; i < numSamples; ++i)
        {
            captureBuffer.setSample (ch, (captureWritePos + i) % captureLength,
                                      buffer.getSample (ch, i));
        }
    }
    captureWritePos = (captureWritePos + numSamples) % captureLength;

    // --- Real DSP chain (AI-decided parameters, already applied via APVTS/EQBand::setParameters) ---
    juce::dsp::AudioBlock<float> block (buffer);

    for (auto& band : eqBands)
        band.process (block);

    dynamics.process (block);
    stereoWidth.process (block);

    auto* outputGainParam = apvts.getRawParameterValue ("outputGain");
    if (outputGainParam != nullptr)
    {
        float gainLinear = juce::Decibels::decibelsToGain (outputGainParam->load());
        buffer.applyGain (gainLinear);
    }
}

juce::AudioProcessorEditor* SundariAudioProcessor::createEditor()
{
    return new SundariAudioProcessorEditor (*this);
}

void SundariAudioProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    auto state = apvts.copyState();
    std::unique_ptr<juce::XmlElement> xml (state.createXml());
    copyXmlToBinary (*xml, destData);
}

void SundariAudioProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    std::unique_ptr<juce::XmlElement> xmlState (getXmlFromBinary (data, sizeInBytes));
    if (xmlState != nullptr && xmlState->hasTagName (apvts.state.getType()))
        apvts.replaceState (juce::ValueTree::fromXml (*xmlState));
}

// ---------------------------------------------------------------------------
// AI Integration
// ---------------------------------------------------------------------------

juce::File SundariAudioProcessor::writeCaptureBufferToTempWav()
{
    auto tempFile = juce::File::getSpecialLocation (juce::File::tempDirectory)
                         .getChildFile ("sundari_capture_" + juce::String (juce::Random::getSystemRandom().nextInt()) + ".wav");

    juce::WavAudioFormat wavFormat;
    std::unique_ptr<juce::FileOutputStream> outStream (tempFile.createOutputStream());

    if (outStream == nullptr)
        return {};

    std::unique_ptr<juce::AudioFormatWriter> writer (
        wavFormat.createWriterFor (outStream.get(), currentSampleRate, 2, 24, {}, 0));

    if (writer == nullptr)
        return {};

    outStream.release(); // writer ab is stream ka owner hai

    // Rolling buffer ko sahi (chronological) order mein likhna — capture-
    // WritePos ke baad wala hissa sabse purana hai, isliye do parts mein
    // likhte hain (jaise ek circular buffer read hota hai).
    writer->writeFromAudioSampleBuffer (
        captureBuffer, captureWritePos, captureBuffer.getNumSamples() - captureWritePos);
    if (captureWritePos > 0)
        writer->writeFromAudioSampleBuffer (captureBuffer, 0, captureWritePos);

    writer.reset(); // flush + close

    return tempFile;
}

void SundariAudioProcessor::requestAIAnalysis()
{
    if (analysisInProgress.exchange (true))
        return; // pehle se ek request chal rahi hai

    auto wavFile = writeCaptureBufferToTempWav();
    if (! wavFile.existsAsFile())
    {
        analysisInProgress.store (false);
        return;
    }

    decisionClient.requestDecisionAsync (
        getName(), trackRole, wavFile,
        [this] (TrackDecisionResult result)
        {
            // Yeh callback juce::MessageManager::callAsync se aata hai
            // (DecisionClient.cpp dekhein) — isliye yahan UI-thread par
            // safely APVTS/parameters touch karna theek hai.
            {
                const juce::ScopedLock lock (lastResultLock);
                lastDecisionResult = result;
            }

            if (result.success)
                applyDecisionToParameters (result);

            analysisInProgress.store (false);
        });
}

TrackDecisionResult SundariAudioProcessor::getLastDecisionResult() const
{
    const juce::ScopedLock lock (lastResultLock);
    return lastDecisionResult;
}

void SundariAudioProcessor::applyDecisionToParameters (const TrackDecisionResult& result)
{
    // NOTE: EQBand::setParameters() aur DynamicsChain::setXParameters()
    // internally IIR coefficients ko ek naye ReferenceCountedObjectPtr se
    // replace karte hain — yeh operation lock-free hai (JUCE ka
    // ProcessorDuplicator isi liye design hua hai), isliye message-thread
    // se yahan call karna audio-thread ke liye safe hai, bina explicit
    // mutex ke.

    int bandIndex = 0;
    for (auto& bandVar : result.eqBands)
    {
        if (bandIndex >= kNumEQBands)
            break;

        float freq = (float) bandVar["frequency_hz"];
        float gain = (float) bandVar["gain_db"];
        float q = (float) bandVar["q_factor"];
        juce::String typeStr = bandVar["filter_type"].toString();

        FilterType type = FilterType::bell;
        if (typeStr == "high_shelf") type = FilterType::highShelf;
        else if (typeStr == "low_shelf") type = FilterType::lowShelf;
        else if (typeStr == "high_pass") type = FilterType::highPass;
        else if (typeStr == "low_pass") type = FilterType::lowPass;
        else if (typeStr == "notch") type = FilterType::notch;

        eqBands[(size_t) bandIndex].setParameters (freq, gain, q, type, true);
        ++bandIndex;
    }
    // Baaki bands (agar AI ne kam bands di hon) inactive kar dein
    for (int i = bandIndex; i < kNumEQBands; ++i)
        eqBands[(size_t) i].setParameters (1000.0f, 0.0f, 1.0f, FilterType::bell, false);

    dynamics.setCompressorParameters (
        result.compressionNeeded, result.compThreshold, result.compRatio,
        result.compAttack, result.compRelease, result.compMakeupGain);

    dynamics.setLimiterParameters (result.limiterNeeded, result.limiterCeiling);

    stereoWidth.setWidthPercent (result.stereoWidthPercent);
}

} // namespace sundari

// This creates new instances of the plugin — JUCE convention, is naam
// (createPluginFilter) ka global scope mein hona zaroori hai.
juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new sundari::SundariAudioProcessor();
}
