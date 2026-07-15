/*
  DecisionClient.cpp
  ====================
  Background thread implementation. `juce::URL::InputStreamOptions` se
  HTTP POST request Python backend ko jaati hai, JSON response parse
  hoke `TrackDecisionResult` mein convert hoti hai.
*/

#include "DecisionClient.h"
#include <juce_events/juce_events.h>

namespace sundari
{

DecisionClient::DecisionClient() : juce::Thread ("Sundari AI Decision Client")
{
    startThread (juce::Thread::Priority::background);
}

DecisionClient::~DecisionClient()
{
    stopThread (2000);
}

void DecisionClient::requestDecisionAsync (const juce::String& trackName,
                                            const juce::String& trackRole,
                                            const juce::File& wavFilePath,
                                            std::function<void (TrackDecisionResult)> onComplete)
{
    {
        const juce::ScopedLock lock (queueLock);
        pendingQueue.push_back ({ trackName, trackRole, wavFilePath, std::move (onComplete) });
    }
    workAvailable.signal();
}

void DecisionClient::run()
{
    while (! threadShouldExit())
    {
        workAvailable.wait (200); // 200ms poll — background thread hai, audio thread nahi, isliye yeh sasta hai

        PendingRequest req;
        bool haveWork = false;
        {
            const juce::ScopedLock lock (queueLock);
            if (! pendingQueue.empty())
            {
                req = pendingQueue.front();
                pendingQueue.erase (pendingQueue.begin());
                haveWork = true;
            }
        }

        if (! haveWork)
            continue;

        auto result = performHttpRequest (req);

        // Temp WAV file ab zaroori nahi — background thread khatam hone
        // ke baad hi delete karte hain (audio thread ka isse koi lena-dena
        // nahi, isliye yeh safe hai).
        if (req.wavFile.existsAsFile())
            req.wavFile.deleteFile();

        // Callback ko message-thread (UI thread) par safely deliver karna
        // — background thread se seedhe UI update karna crash-prone hota
        // hai, isliye juce::MessageManager::callAsync use karte hain.
        auto callback = req.callback;
        juce::MessageManager::callAsync ([callback, result]
        {
            if (callback)
                callback (result);
        });
    }
}

TrackDecisionResult DecisionClient::performHttpRequest (const PendingRequest& req)
{
    TrackDecisionResult result;

    if (! req.wavFile.existsAsFile())
    {
        result.success = false;
        result.errorMessage = "Temporary WAV file nahi mili — capture buffer likhne mein samasya hui.";
        return result;
    }

    juce::URL url (backendBaseUrl + "/api/v1/decision/project");

    // Backend endpoint (`routes_decision.py::decide_project`) `files`
    // (multipart) + `roles` (form field, comma-separated) maangta hai —
    // hum ek single-track request bhejte hain isliye `roles` mein sirf
    // ek role hota hai.
    url = url.withFileToUpload ("files", req.wavFile, "audio/wav");
    url = url.withParameter ("roles", req.trackRole);

    juce::URL::InputStreamOptions options (juce::URL::ParameterHandling::inPostData);
    options = options.withConnectionTimeoutMs (60000); // AI call mein LLM latency lagti hai, isliye generous timeout

    std::unique_ptr<juce::InputStream> stream (url.createInputStream (options));

    if (stream == nullptr)
    {
        result.success = false;
        result.errorMessage = "Backend se connect nahi ho paya. Kya Python server "
                               "(uvicorn app.main:app) chal raha hai " + backendBaseUrl + " par?";
        return result;
    }

    auto responseText = stream->readEntireStreamAsString();
    return parseResponseJson (responseText);
}

TrackDecisionResult DecisionClient::parseResponseJson (const juce::String& jsonText)
{
    TrackDecisionResult result;

    auto parsed = juce::JSON::parse (jsonText);
    if (! parsed.isObject())
    {
        result.success = false;
        result.errorMessage = "AI backend se invalid JSON response mila.";
        return result;
    }

    // Response ProjectMixDecision schema follow karta hai (dekhein
    // decision_schema.py) — pehla track_decisions[0] is client ke liye
    // relevant hota hai (ek plugin instance = ek track).
    auto* trackDecisions = parsed["track_decisions"].getArray();
    if (trackDecisions == nullptr || trackDecisions->isEmpty())
    {
        result.success = false;
        result.errorMessage = "Response mein koi track decision nahi mila.";
        return result;
    }

    auto decision = trackDecisions->getReference (0);

    if (auto* eqArray = decision["eq_bands"].getArray())
        for (auto& band : *eqArray)
            result.eqBands.add (band);

    auto compression = decision["compression"];
    result.compressionNeeded = (bool) compression["needed"];
    if (result.compressionNeeded)
    {
        result.compThreshold = (float) compression["threshold_db"];
        result.compRatio = (float) compression["ratio"];
        result.compAttack = (float) compression["attack_ms"];
        result.compRelease = (float) compression["release_ms"];
        result.compMakeupGain = (float) compression["makeup_gain_db"];
    }

    if (decision["stereo"].isObject())
        result.stereoWidthPercent = (float) decision["stereo"]["width_adjustment_percent"];

    auto teaching = decision["teaching_explanation"];
    result.whatWasTheProblem = teaching["what_was_the_problem"].toString();
    result.whyItWasAProblem = teaching["why_it_was_a_problem"].toString();
    result.whatWasChanged = teaching["what_was_changed"].toString();
    result.whyThisChange = teaching["why_this_change"].toString();
    result.expectedDifference = teaching["expected_difference"].toString();
    result.whatIfNotFixed = teaching["what_if_not_fixed"].toString();
    result.professionalReasoning = teaching["professional_reasoning"].toString();
    result.confidence = (float) decision["confidence"];

    result.success = true;
    return result;
}

} // namespace sundari
