/*
  PluginProcessor.h
  ===================
  Sundari AI Mix Engineer ka core `juce::AudioProcessor`. Yahi class hai
  jo Logic Pro (ya kisi bhi AU/VST3 host) load karta hai.

  Architecture summary:
  - Real-time `processBlock()` sirf DSP chain (EQBand + DynamicsChain +
    StereoWidthProcessor) run karta hai — yeh kabhi block/wait nahi karta.
  - AI decisions background thread (`DecisionClient`) se async aati hain;
    naye parameters ek atomic "pending update" struct mein store hote hain
    aur agle `processBlock()` call ke shuru mein safely apply hote hain
    (audio-thread-safe parameter handoff, koi lock audio thread par nahi).
  - `AudioProcessorValueTreeState` (APVTS) se saare parameters host ke
    automation system se bhi connected hote hain — isse Logic Pro ka
    automation lane bhi in values ko record/playback kar sakta hai.
*/

#pragma once

#include <JuceHeader.h>
#include "DSP/EQBand.h"
#include "DSP/DynamicsChain.h"
#include "DSP/StereoWidthProcessor.h"
#include "AI/DecisionClient.h"
#include <array>
#include <atomic>

namespace sundari
{

static constexpr int kNumEQBands = 6;

class SundariAudioProcessor : public juce::AudioProcessor
{
public:
    SundariAudioProcessor();
    ~SundariAudioProcessor() override;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;
    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return "Sundari AI Mix Engineer"; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    double getTailLengthSeconds() const override { return 0.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return {}; }
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    // --- Editor (UI) yeh methods use karta hai ---

    // "Analyze karo aur AI se suggestion maango" — Editor ke button se
    // trigger hota hai. Yeh khud audio buffer ko capture karke (last N
    // seconds ka rolling buffer), uska analysis JSON banata hai, aur
    // background thread par backend ko bhejta hai.
    void requestAIAnalysis();

    // Editor ko current AI response dikhane ke liye (Learning Mode panel)
    TrackDecisionResult getLastDecisionResult() const;
    bool isAnalysisInProgress() const { return analysisInProgress.load(); }

    // Editor ke dropdown se set hota hai — "lead_vocal", "kick", "bass",
    // "master", waghera. Backend ke Phase 2 role-specific rules aur
    // Phase 4 AI dono isko context ke roop mein use karte hain.
    void setTrackRole (const juce::String& role) { trackRole = role; }
    juce::String getTrackRole() const { return trackRole; }

    juce::AudioProcessorValueTreeState apvts;

    DecisionClient& getDecisionClient() { return decisionClient; }

private:
    juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();

    // Naya AI decision aane par yeh call hota hai (message thread se) —
    // yeh sirf ek "pending" flag set karta hai; asli DSP-object update
    // agle processBlock() ke start mein hota hai (audio-thread-safe).
    void applyDecisionToParameters (const TrackDecisionResult& result);

    std::array<EQBand, kNumEQBands> eqBands;
    DynamicsChain dynamics;
    StereoWidthProcessor stereoWidth;

    DecisionClient decisionClient;

    std::atomic<bool> analysisInProgress { false };
    juce::CriticalSection lastResultLock;
    TrackDecisionResult lastDecisionResult;

    // Rolling capture buffer — "Analyze karo" click hone par pichle
    // ~10 second ka audio isme collect hota hai taaki backend ko bhejne
    // ke liye ek sample mile (offline WAV export ki tarah, lekin plugin
    // ke andar hi).
    juce::AudioBuffer<float> captureBuffer;
    int captureWritePos = 0;
    double currentSampleRate = 44100.0;
    juce::String trackRole { "generic" };

    juce::File writeCaptureBufferToTempWav();

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SundariAudioProcessor)
};

} // namespace sundari
