/*
  DecisionClient.h
  =================
  Plugin ko humare Python Decision Engine backend (Phase 4,
  `backend/app/api/routes_decision.py`) se jodta hai.

  CRITICAL real-time audio rule: audio thread (`processBlock()`) kabhi
  bhi network call, disk I/O, ya kisi bhi blocking operation ka wait NAHI
  kar sakta — isse audio dropout/glitch hota hai. Isliye yeh class
  `juce::Thread` par background mein chalti hai; jab AI response aa
  jaata hai, naye parameters ek lock-free `std::atomic`/message-queue
  mechanism se audio thread tak pahunchte hain (dekhein
  PluginProcessor.h mein `juce::AbstractFifo` / atomic flag ka use).
*/

#pragma once

#include <juce_core/juce_core.h>
#include <functional>

namespace sundari
{

struct TrackDecisionResult
{
    bool success = false;
    juce::String errorMessage;

    // Parsed AI decision fields (decision_schema.py ke TrackMixDecision se)
    juce::Array<juce::var> eqBands;   // har element: {frequency_hz, gain_db, q_factor, filter_type}
    bool compressionNeeded = false;
    float compThreshold = -18.0f, compRatio = 2.0f, compAttack = 10.0f,
          compRelease = 100.0f, compMakeupGain = 0.0f;
    bool limiterNeeded = false;
    float limiterCeiling = -1.0f;
    float stereoWidthPercent = 0.0f;

    // AI Teacher / Learning Mode fields
    juce::String whatWasTheProblem, whyItWasAProblem, whatWasChanged,
                 whyThisChange, expectedDifference, whatIfNotFixed,
                 professionalReasoning;
    float confidence = 0.0f;
};

class DecisionClient : private juce::Thread
{
public:
    DecisionClient();
    ~DecisionClient() override;

    // Plugin ki settings screen se backend URL configurable hai (default:
    // local FastAPI server, http://localhost:8000) — isse producer chahe
    // to apna cloud-hosted backend bhi point kar sakta hai.
    void setBackendUrl (const juce::String& url) { backendBaseUrl = url; }

    // Non-blocking: request queue mein daal deta hai, background thread
    // process karti hai, result callback (message-thread par safely
    // deliver hota hai) se wapas aata hai.
    //
    // `wavFilePath` — ek temporary WAV file jo Plugin Processor ne rolling
    // capture buffer se likhi hai (dekhein PluginProcessor::requestAIAnalysis).
    // Hum audio ko JSON mein embed NAHI karte (woh bahut inefficient/bada
    // hota hai) — backend ke existing multipart file-upload endpoints
    // (`/api/v1/decision/project`) ke saath consistent rehne ke liye
    // asli file upload karte hain, bilkul jaise web/desktop client karta.
    void requestDecisionAsync (const juce::String& trackName,
                                const juce::String& trackRole,
                                const juce::File& wavFilePath,
                                std::function<void (TrackDecisionResult)> onComplete);

private:
    void run() override;  // juce::Thread override — background worker loop

    juce::String backendBaseUrl { "http://localhost:8000" };

    struct PendingRequest
    {
        juce::String trackName;
        juce::String trackRole;
        juce::File wavFile;
        std::function<void (TrackDecisionResult)> callback;
    };

    juce::CriticalSection queueLock;
    std::vector<PendingRequest> pendingQueue;
    juce::WaitableEvent workAvailable;

    TrackDecisionResult performHttpRequest (const PendingRequest& req);
    TrackDecisionResult parseResponseJson (const juce::String& jsonText);

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (DecisionClient)
};

} // namespace sundari
