/*
  PluginEditor.cpp
  ==================
*/

#include "PluginEditor.h"

namespace sundari
{

SundariAudioProcessorEditor::SundariAudioProcessorEditor (SundariAudioProcessor& p)
    : AudioProcessorEditor (&p), audioProcessor (p)
{
    setSize (520, 480);

    // --- Brand assets ---
    sundariLogo = juce::ImageCache::getFromMemory (
        SundariAIMixEngineerAssets::sundari_logo_png, SundariAIMixEngineerAssets::sundari_logo_pngSize);
    artistPhoto = juce::ImageCache::getFromMemory (
        SundariAIMixEngineerAssets::artist_photo_jpg, SundariAIMixEngineerAssets::artist_photo_jpgSize);

    // --- Role selector ---
    roleSelector.addItemList (
        { "generic", "lead_vocal", "backing_vocal", "kick", "snare", "bass",
          "guitar", "keys", "master" }, 1);
    roleSelector.setSelectedItemIndex (0, juce::dontSendNotification);
    roleSelector.onChange = [this]
    {
        audioProcessor.setTrackRole (roleSelector.getText());
    };
    addAndMakeVisible (roleSelector);

    // --- Analyze button ---
    analyzeButton.onClick = [this]
    {
        audioProcessor.requestAIAnalysis();
        statusLabel.setText ("AI se poochh rahe hain... (isme kuch second lag sakte hain)",
                              juce::dontSendNotification);
    };
    addAndMakeVisible (analyzeButton);

    statusLabel.setText ("Tayyar — 'Analyze' dabayein jab track kuch der baj rahi ho.",
                          juce::dontSendNotification);
    statusLabel.setJustificationType (juce::Justification::centredLeft);
    addAndMakeVisible (statusLabel);

    // --- Manual controls (AI ke upar user override) ---
    addAndMakeVisible (bypassLabel);
    bypassToggle.setButtonText ({});
    addAndMakeVisible (bypassToggle);
    bypassAttachment = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (
        audioProcessor.apvts, "bypass", bypassToggle);

    outputGainSlider.setSliderStyle (juce::Slider::LinearHorizontal);
    outputGainSlider.setTextBoxStyle (juce::Slider::TextBoxRight, false, 60, 20);
    addAndMakeVisible (outputGainSlider);
    addAndMakeVisible (outputGainLabel);
    outputGainAttachment = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (
        audioProcessor.apvts, "outputGain", outputGainSlider);

    // --- Learning Mode / AI Teacher explanation panel ---
    explanationPanel.setMultiLine (true);
    explanationPanel.setReadOnly (true);
    explanationPanel.setScrollbarsShown (true);
    explanationPanel.setText (
        "AI Teacher Panel\n\n"
        "Jab aap 'Analyze' dabayenge, AI ka poora reasoning yahan dikhega — "
        "samasya kya thi, kyun thi, AI ne kya badla, kyun badla, aur "
        "professional engineers is baare mein kya sochte hain.");
    addAndMakeVisible (explanationPanel);

    confidenceLabel.setJustificationType (juce::Justification::centredRight);
    addAndMakeVisible (confidenceLabel);

    startTimerHz (5); // AI response ka status poll karne ke liye
}

SundariAudioProcessorEditor::~SundariAudioProcessorEditor()
{
    stopTimer();
}

void SundariAudioProcessorEditor::paint (juce::Graphics& g)
{
    g.fillAll (juce::Colour (0xff1a1a1f)); // Dark theme (spec: "Professional Dark Theme")

    g.setColour (juce::Colours::white);
    g.setFont (juce::FontOptions (20.0f, juce::Font::bold));
    g.drawFittedText ("Sundari AI Mix Engineer", getLocalBounds().removeFromTop (40),
                       juce::Justification::centred, 1);
}

void SundariAudioProcessorEditor::resized()
{
    auto area = getLocalBounds().reduced (12);
    area.removeFromTop (40); // title space

    auto topRow = area.removeFromTop (30);
    roleSelector.setBounds (topRow.removeFromLeft (200));
    topRow.removeFromLeft (8);
    analyzeButton.setBounds (topRow);

    area.removeFromTop (8);
    statusLabel.setBounds (area.removeFromTop (24));

    area.removeFromTop (12);
    auto controlsRow = area.removeFromTop (30);
    bypassLabel.setBounds (controlsRow.removeFromLeft (60));
    bypassToggle.setBounds (controlsRow.removeFromLeft (40));
    controlsRow.removeFromLeft (20);
    outputGainLabel.setBounds (controlsRow.removeFromLeft (90));
    outputGainSlider.setBounds (controlsRow);

    area.removeFromTop (12);
    confidenceLabel.setBounds (area.removeFromTop (20));

    area.removeFromTop (8);
    explanationPanel.setBounds (area);
}

void SundariAudioProcessorEditor::timerCallback()
{
    if (audioProcessor.isAnalysisInProgress())
        return;

    auto result = audioProcessor.getLastDecisionResult();
    if (! result.success && result.errorMessage.isEmpty())
        return; // abhi tak koi request complete nahi hui

    updateExplanationPanel (result);
}

void SundariAudioProcessorEditor::updateExplanationPanel (const TrackDecisionResult& result)
{
    if (! result.success)
    {
        statusLabel.setText ("Error: " + result.errorMessage, juce::dontSendNotification);
        return;
    }

    statusLabel.setText ("AI decision mil gaya.", juce::dontSendNotification);
    confidenceLabel.setText (
        "AI Confidence: " + juce::String (result.confidence * 100.0f, 1) + "%",
        juce::dontSendNotification);

    juce::String text;
    text << "SAMASYA KYA THI:\n" << result.whatWasTheProblem << "\n\n";
    text << "YEH SAMASYA KYUN THI:\n" << result.whyItWasAProblem << "\n\n";
    text << "AI NE KYA BADLA:\n" << result.whatWasChanged << "\n\n";
    text << "KYUN BADLA:\n" << result.whyThisChange << "\n\n";
    text << "ISSE KYA ANTAR AAYEGA:\n" << result.expectedDifference << "\n\n";
    text << "AGAR NA BADALTE TO:\n" << result.whatIfNotFixed << "\n\n";
    text << "PROFESSIONAL ENGINEER AISA KYUN KARTE HAIN:\n" << result.professionalReasoning;

    explanationPanel.setText (text, juce::dontSendNotification);
}

} // namespace sundari
