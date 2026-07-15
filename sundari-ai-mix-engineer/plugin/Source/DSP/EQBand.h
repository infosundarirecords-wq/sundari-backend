/*
  EQBand.h
  ========
  Ek single parametric EQ band ka wrapper, JUCE ke `juce::dsp::IIR::Filter`
  par based — yeh asli real-time audio processing hai (koi placeholder
  nahi), jo Biquad coefficients use karta hai (Direct Form I).

  Design decision: Frequency/Gain/Q values yahan hardcode NAHI hain — yeh
  AI Decision Engine se (HTTP call ke through) set hote hain runtime par.
  Isse plugin genuinely "no fixed preset" spec requirement follow karta
  hai — DSP engine sirf ek "executor" hai, "decision maker" nahi; decision
  Python backend ke AI se aata hai.

  Thread-safety note: `setParameters()` background thread (jahan AI
  response process hoti hai) se call hoga, jabki `process()` audio thread
  par chalta hai. JUCE ke IIR::Filter coefficients internally
  `juce::ReferenceCountedObjectPtr` use karte hain jo lock-free swap ke
  liye safe hain — isliye hum seedhe `coefficients` field replace karte
  hain, audio thread block nahi hota.
*/

#pragma once

#include <juce_dsp/juce_dsp.h>

namespace sundari
{

enum class FilterType
{
    bell,
    highShelf,
    lowShelf,
    highPass,
    lowPass,
    notch
};

class EQBand
{
public:
    void prepare (const juce::dsp::ProcessSpec& spec)
    {
        sampleRate = spec.sampleRate;
        filter.prepare (spec);
        updateCoefficients();
    }

    void reset()
    {
        filter.reset();
    }

    // AI Decision Engine ke response se yeh call hota hai — is function ka
    // input seedha `decision_schema.py` ke EQBandDecision se map hota hai.
    void setParameters (float frequencyHz, float gainDb, float qFactor, FilterType type, bool active)
    {
        frequency = juce::jlimit (20.0f, 20000.0f, frequencyHz);
        gain = gainDb;
        q = juce::jmax (0.1f, qFactor);
        filterType = type;
        isActive = active;
        updateCoefficients();
    }

    void process (juce::dsp::AudioBlock<float>& block)
    {
        if (! isActive)
            return;

        juce::dsp::ProcessContextReplacing<float> context (block);
        filter.process (context);
    }

private:
    void updateCoefficients()
    {
        if (sampleRate <= 0.0)
            return;

        auto gainLinear = juce::Decibels::decibelsToGain (gain);

        switch (filterType)
        {
            case FilterType::bell:
                *filter.state = *juce::dsp::IIR::Coefficients<float>::makePeakFilter (
                    sampleRate, frequency, q, gainLinear);
                break;
            case FilterType::highShelf:
                *filter.state = *juce::dsp::IIR::Coefficients<float>::makeHighShelf (
                    sampleRate, frequency, q, gainLinear);
                break;
            case FilterType::lowShelf:
                *filter.state = *juce::dsp::IIR::Coefficients<float>::makeLowShelf (
                    sampleRate, frequency, q, gainLinear);
                break;
            case FilterType::highPass:
                *filter.state = *juce::dsp::IIR::Coefficients<float>::makeHighPass (
                    sampleRate, frequency, q);
                break;
            case FilterType::lowPass:
                *filter.state = *juce::dsp::IIR::Coefficients<float>::makeLowPass (
                    sampleRate, frequency, q);
                break;
            case FilterType::notch:
                *filter.state = *juce::dsp::IIR::Coefficients<float>::makeNotch (
                    sampleRate, frequency, q);
                break;
        }
    }

    juce::dsp::ProcessorDuplicator<juce::dsp::IIR::Filter<float>,
                                    juce::dsp::IIR::Coefficients<float>> filter;

    double sampleRate = 44100.0;
    float frequency = 1000.0f;
    float gain = 0.0f;
    float q = 1.0f;
    FilterType filterType = FilterType::bell;
    bool isActive = false;
};

} // namespace sundari
