/*
  DynamicsChain.h
  ================
  Compressor + Limiter, JUCE ke built-in `juce::dsp::Compressor` aur
  `juce::dsp::Limiter` classes par based — dono asli, sample-accurate
  real-time dynamics processing hain.

  Spec ke "Threshold, Ratio, Attack, Release, Makeup Gain — sab AI decide
  karega, koi fixed value nahi" requirement ke mutabiq, is class mein
  koi default "achha lagta hai" wala value hardcode nahi kiya gaya —
  saare parameters `setParameters()` ke through AI Decision Engine se
  aate hain. Agar AI kabhi call na kare (jaise offline/no-API-key
  scenario), compressor "needed=false" state mein bypass rehta hai,
  chup-chaap koi fixed processing apply nahi karta.
*/

#pragma once

#include <juce_dsp/juce_dsp.h>

namespace sundari
{

class DynamicsChain
{
public:
    void prepare (const juce::dsp::ProcessSpec& spec)
    {
        compressor.prepare (spec);
        limiter.prepare (spec);
        makeupGain.prepare (spec);
        makeupGain.setRampDurationSeconds (0.05);
    }

    void reset()
    {
        compressor.reset();
        limiter.reset();
        makeupGain.reset();
    }

    // Compression AI Decision Engine se — dekhein decision_schema.py ka
    // CompressionDecision.
    void setCompressorParameters (bool needed, float thresholdDb, float ratio,
                                   float attackMs, float releaseMs, float makeupGainDb)
    {
        compressorActive = needed;
        if (! needed)
            return;

        compressor.setThreshold (thresholdDb);
        compressor.setRatio (juce::jmax (1.0f, ratio));
        compressor.setAttack (juce::jmax (0.1f, attackMs));
        compressor.setRelease (juce::jmax (1.0f, releaseMs));
        makeupGain.setGainDecibels (makeupGainDb);
    }

    // Limiter AI Decision Engine se — dekhein decision_schema.py ka
    // LimiterDecision. `ceilingDbtp` yahan sample-peak ceiling ke roop
    // mein use hota hai; asli true-peak limiting ke liye oversampling
    // add karna future enhancement hai (dekhein README mein limitation
    // note).
    void setLimiterParameters (bool needed, float ceilingDbtp)
    {
        limiterActive = needed;
        if (! needed)
            return;
        limiter.setThreshold (ceilingDbtp);
        limiter.setRelease (50.0f);
    }

    void process (juce::dsp::AudioBlock<float>& block)
    {
        juce::dsp::ProcessContextReplacing<float> context (block);

        if (compressorActive)
        {
            compressor.process (context);
            makeupGain.process (context);
        }

        if (limiterActive)
            limiter.process (context);
    }

private:
    juce::dsp::Compressor<float> compressor;
    juce::dsp::Limiter<float> limiter;
    juce::dsp::Gain<float> makeupGain;

    bool compressorActive = false;
    bool limiterActive = false;
};

} // namespace sundari
