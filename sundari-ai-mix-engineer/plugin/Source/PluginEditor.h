/*
  PluginEditor.h
  ===============
  Minimal, functional UI — spec ke "AI Teacher" requirement ke mutabiq
  is editor ka focus explanation panel par hai, complicated skeuomorphic
  knobs par nahi (woh Phase 8/UI-polish ka kaam hai; yeh Phase 4 ka goal
  hai: AI Decision Engine ko genuinely plugin ke andar se kaam karke
  dikhana).
*/

#pragma once

#include <JuceHeader.h>
#include "PluginProcessor.h"

namespace sundari
{

class SundariAudioProcessorEditor : public juce::AudioProcessorEditor,
                                     private juce::Timer
{
public:
    explicit SundariAudioProcessorEditor (SundariAudioProcessor&);
    ~SundariAudioProcessorEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

private:
    void timerCallback() override;  // AI response poll karne ke liye (analysisInProgress state)
    void updateExplanationPanel (const TrackDecisionResult& result);

    SundariAudioProcessor& audioProcessor;

    juce::TextButton analyzeButton { "AI se Analyze aur Suggest karein" };
    juce::ComboBox roleSelector;
    juce::Label statusLabel;

    juce::Label bypassLabel { {}, "Bypass" };
    juce::ToggleButton bypassToggle;
    std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment> bypassAttachment;

    juce::Slider outputGainSlider;
    juce::Label outputGainLabel { {}, "Output Gain" };
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> outputGainAttachment;

    // Learning Mode panel — AI Teacher explanation yahan dikhti hai
    juce::TextEditor explanationPanel;
    juce::Label confidenceLabel;

    // Brand assets — logo top par, artist photo corner mein (BinaryData se load hote hain)
    juce::Image sundariLogo;
    juce::Image artistPhoto;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SundariAudioProcessorEditor)
};

} // namespace sundari
