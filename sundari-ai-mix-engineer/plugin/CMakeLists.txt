# Sundari AI Mix Engineer — Plugin CMakeLists.txt
#
# Yeh JUCE ka modern CMake API use karta hai (Projucer nahi). Isse VST3
# aur AU (Audio Unit, jo Logic Pro use karta hai) dono formats build
# hote hain ek hi source se.
#
# Build karne se pehle JUCE library chahiye — dekhein
# docs/BUILD_INSTRUCTIONS_MAC.md mein poore steps.

cmake_minimum_required(VERSION 3.22)

project(SundariAIMixEngineer VERSION 0.1.0)

# JUCE ko FetchContent se automatically clone kiya jaata hai — isse aapko
# manually JUCE download karke path set karne ki zaroorat nahi.
include(FetchContent)
FetchContent_Declare(
    JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG 7.0.12
)
FetchContent_MakeAvailable(JUCE)

juce_add_plugin(SundariAIMixEngineer
    COMPANY_NAME "Sundari AI"
    PLUGIN_MANUFACTURER_CODE Sund
    PLUGIN_CODE Smx1
    FORMATS AU VST3 Standalone
    PRODUCT_NAME "Sundari AI Mix Engineer"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD TRUE
    VST3_CATEGORIES "Fx" "EQ" "Dynamics"
    AU_MAIN_TYPE "kAudioUnitType_Effect"
)

juce_generate_juce_header(SundariAIMixEngineer)

# --- Brand assets (logo + photo) ko binary data ke roop mein embed karna ---
# Isse images plugin ke andar hi compile ho jaati hain — install karte
# waqt alag se image files copy karne ki zaroorat nahi padti.
juce_add_binary_data(SundariAIMixEngineerAssets
    SOURCES
        Assets/sundari_logo.png
        Assets/artist_photo.jpg
)

target_sources(SundariAIMixEngineer
    PRIVATE
        Source/PluginProcessor.cpp
        Source/PluginEditor.cpp
        Source/AI/DecisionClient.cpp
)

target_compile_definitions(SundariAIMixEngineer
    PUBLIC
        JUCE_WEB_BROWSER=0
        JUCE_USE_CURL=1
        JUCE_VST3_CAN_REPLACE_VST2=0
)

target_link_libraries(SundariAIMixEngineer
    PRIVATE
        SundariAIMixEngineerAssets
        juce::juce_audio_utils
        juce::juce_dsp
        juce::juce_core
        juce::juce_events
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_lto_flags
        juce::juce_recommended_warning_flags
)
