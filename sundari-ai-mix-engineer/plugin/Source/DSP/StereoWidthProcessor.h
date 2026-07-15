/*
  StereoWidthProcessor.h
  =======================
  Mid-Side (M/S) encoding/decoding se stereo width control — yeh wahi
  technique hai jo professional stereo imaging plugins (Waves S1,
  iZotope Ozone Imager) internally use karte hain.

  Math: Mid = (L+R)/2, Side = (L-R)/2. Side ko multiply karke width badhti
  /ghatati hai; phir L = Mid + Side, R = Mid - Side se wapas convert hota
  hai. `widthAmount = 1.0` ka matlab hai "koi badlaav nahi" (original
  stereo image), 0.0 = mono, 2.0 = double-wide.
*/

#pragma once

#include <juce_dsp/juce_dsp.h>

namespace sundari
{

class StereoWidthProcessor
{
public:
    void setWidthPercent (float widthAdjustmentPercent)
    {
        // AI se "+30%" ya "-20%" jaisa relative adjustment aata hai;
        // 1.0 = neutral baseline, +100% => 2.0 (double wide), -100% => 0.0 (mono).
        widthAmount = juce::jlimit (0.0f, 2.0f, 1.0f + (widthAdjustmentPercent / 100.0f));
    }

    void process (juce::dsp::AudioBlock<float>& block)
    {
        if (block.getNumChannels() < 2)
            return; // Mono signal par stereo width lagoo nahi hoti

        auto* left = block.getChannelPointer (0);
        auto* right = block.getChannelPointer (1);
        auto numSamples = block.getNumSamples();

        for (size_t i = 0; i < numSamples; ++i)
        {
            float mid = (left[i] + right[i]) * 0.5f;
            float side = (left[i] - right[i]) * 0.5f;

            side *= widthAmount;

            left[i] = mid + side;
            right[i] = mid - side;
        }
    }

private:
    float widthAmount = 1.0f;
};

} // namespace sundari
