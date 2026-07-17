# =============================================================================
# config.py – Global constants for Color Match
# =============================================================================

# --- Window ------------------------------------------------------------------
WIDTH  = 720
HEIGHT = 720
FPS    = 60
TARGET_DISPLAY_TIME = 5.0   # seconds the target colour is shown before mixing

# --- Match-screen layout (all in pixels) -------------------------------------
SLIDER_AREA_H = 140    # bottom strip that holds the three channel bars

# Triangle area fills everything above the slider strip
TRI_AREA_W = WIDTH                      # 720
TRI_AREA_H = HEIGHT - SLIDER_AREA_H    # 580

# Keyboard-slider bar centres (evenly spaced across the full width)
SLIDER_Y  = HEIGHT - SLIDER_AREA_H // 2    # 650
SLIDER_XS = [
    WIDTH // 4,          # 180  Red
    WIDTH // 2,          # 360  Green
    WIDTH * 3 // 4,      # 540  Blue
]

# --- Colour palette (dark theme) ---------------------------------------------
BG        = ( 12,  12,  20)
PANEL_BG  = ( 22,  22,  34)
TEXT      = (235, 235, 245)
MUTED     = (140, 140, 165)
ACCENT    = (100,  85, 255)
DIVIDER   = ( 38,  38,  55)
SUCCESS   = ( 70, 200,  95)
WARNING   = (210, 175,  50)
DANGER    = (210,  65,  65)

# --- Accuracy thresholds (%) -------------------------------------------------
EXCELLENT_THRESHOLD = 90
GOOD_THRESHOLD      = 75