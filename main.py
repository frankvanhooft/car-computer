from math import floor
from machine import Pin, UART, ADC
from micropyGPS import MicropyGPS
from pimoroni import Button
from picographics import PicoGraphics, DISPLAY_PICO_DISPLAY_2, PEN_RGB332
import jpegdec
import time

my_gps = MicropyGPS()
uart = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5))
adc = ADC(Pin(26))
button_a = Button(12)
METRIC = 1
IMPERIAL = 2
units = METRIC
DIRECTIONS = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')
debug_char = "o"

SCREEN_UPDATE_INTERVAL_MS = 1000

MIN_BACKLIGHT_LEVEL = 0.5
MAX_BACKLIGHT_LEVEL = 1.0
MAX_AMBIENT_LEVEL = 180.0
BACKLIGHT_ADJUST_STEP = 0.05

# We use the RBG332 colorspace because we're displaying JPG images for the compass
display = PicoGraphics(display=DISPLAY_PICO_DISPLAY_2, pen_type=PEN_RGB332, rotate=0)
backlight_level = 0.5
display.set_backlight(backlight_level)
display.set_font("sans")
display.set_thickness(4)

j = jpegdec.JPEG(display)

WHITE = display.create_pen(255, 255, 255)
BLUE_LINE = display.create_pen(42, 146, 255)
BACKGROUND_BLUE = display.create_pen(0, 85, 218)



# clear the screen
def clear_screen():
    display.set_pen(BACKGROUND_BLUE)
    display.clear()
    display.update()


# Calculates & returns the average ambient light value
def ambient_light_value(adc_sum_val, adc_num_vals):
    if adc_num_vals == 0:
        return 0
    adc_average = adc_sum_val / adc_num_vals
    return 0.01007 * adc_average


# Adjusts the backlight level based upon the ambient light.
# Returns the new current backlight level
def update_backlight(ambient_light, current_backlight):
    target_backlight = (ambient_light / MAX_AMBIENT_LEVEL) * MAX_BACKLIGHT_LEVEL
    
    # check & respond if we need to go brighter or dimmer
    if target_backlight > current_backlight:
        current_backlight += BACKLIGHT_ADJUST_STEP
    elif target_backlight < current_backlight:
        current_backlight -= BACKLIGHT_ADJUST_STEP
    
    # ensure new backlight value doesn't go out of bounds
    if current_backlight > MAX_BACKLIGHT_LEVEL:
        current_backlight = MAX_BACKLIGHT_LEVEL
    elif current_backlight < MIN_BACKLIGHT_LEVEL:
        current_backlight = MIN_BACKLIGHT_LEVEL
    
    display.set_backlight(current_backlight)
    return current_backlight


# Print on the screen the number of satellites in view
def display_sats_in_view():
    display.set_pen(WHITE)
    display.set_thickness(2)
    display.text("Acquiring", 5, 40, 160, 1.0)
    display.text("....", 5, 70, 160, 1.0)
    display.text("satellites", 5, 120, 160, 1.0)
    display.text("in view:", 10, 160, 160, 1.0)
    text_string = '{:d}'.format(my_gps.satellites_in_view)
    display.text(text_string, 50, 200, 160, 1.0)
    display.set_thickness(4)

# Asks the GPS for the current heading, and returns a compass direction string, eg "NE"
def compass_direction_string_get():
   # Each compass point is separated by 45 degrees, rotate & divide to find lookup value
    bearing = my_gps.course + 22.5
    if bearing >= 360:
        bearing = bearing - 360
    dir_index = floor(bearing / 45)
    return DIRECTIONS[dir_index]


# Accepts a text direction (eg "NE") and returns a corresponding compass filename
def compass_filename_get(direction):
    filename = "compass-160-" + direction + ".jpg"
    return filename


# Display the compass JPG and direction text
# Only displays compass image and direction if GPS fix is 2D or 3D,
# otherwise displays some satellite information
def display_compass_and_direction():
    if my_gps.fix_type == 2 or my_gps.fix_type == 3:
        direction_string = compass_direction_string_get()
        j.open_file(compass_filename_get(direction_string))
        j.decode(2, 4, jpegdec.JPEG_SCALE_FULL, dither=False)
        display.set_pen(WHITE)
        display.text(direction_string, 60, 205, 160, 1.5)
    else:
        display_sats_in_view()
   

# Display the speed
# Only displays speed if GPS fix is 2D or 3D, otherwise displays "--"
# km/h or mph depending upon units
def display_speed():
    display.set_pen(WHITE)
    units_string = "km/h" if units == METRIC else "mph"
    display.text(units_string, 200, 85, 319, 1.0)

    if my_gps.fix_type == 2 or my_gps.fix_type == 3:
        units_index = 2 if units == METRIC else 1
        text_string = "{:.0f}".format(my_gps.speed[units_index])
        display.text(text_string, 200, 35, 319, 1.4)
    else:
        display.text("--", 200, 35, 319, 1.4)


# Display the altitude
# Only displays altitude if GPS fix is 3D, otherwise displays "--"
# metres or feet depending upon units
def display_altitude():
    display.set_pen(WHITE)
    units_string = "m" if units == METRIC else "ft"
    display.text(units_string, 200, 210, 319, 1.0)
    
    if my_gps.fix_type == 3:
        altitude = my_gps.altitude if units == METRIC else my_gps.altitude * 3.28084
        xpos = 197 if altitude < 1000 else 175
        text_string = "{:.0f}".format(altitude)
        display.text(text_string, xpos, 170, 319, 1.4)
    else:
        display.text("--", 200, 170, 319, 1.4)


# Draw a horizontal line separating speed and altitude
def display_line():
    display.set_pen(BLUE_LINE)
    display.line(170, 125, 310, 125, 4)


# Set up
clear_screen()
screen_update_deadline = time.ticks_add(time.ticks_ms(), SCREEN_UPDATE_INTERVAL_MS)
adc_data_running_sum = 0
adc_sample_count = 0

# Main Loop
while True:
    # Process any received GPS UART messages (or part thereof)
    if uart.any():
        gps_sentence = str(uart.readline())[2:-1]
        for x in gps_sentence:
            my_gps.update(x)
            
    # Grab an ADC sample for the ambient light sensor
    adc_data_running_sum += adc.read_u16()
    adc_sample_count += 1
    
    # flip the units if a button press is detected
    if button_a.read():
        units = IMPERIAL if units == METRIC else METRIC
            
    # Periodically update the display, including backlight level
    if (time.ticks_diff(time.ticks_ms(), screen_update_deadline) > 0):
        screen_update_deadline = time.ticks_add(time.ticks_ms(), SCREEN_UPDATE_INTERVAL_MS)
        
        # update light sensor ADC variables
        ambient_light_level = ambient_light_value(adc_data_running_sum, adc_sample_count)
        adc_data_running_sum = 0
        adc_sample_count = 0
        
        # update screen brightness
        backlight_level = update_backlight(ambient_light_level, backlight_level)
    
        # update contents of the display
        display.set_pen(BACKGROUND_BLUE)
        display.clear()
        display_compass_and_direction()
        display_speed()
        display_line()
        display_altitude()
        
        # debug only - toggle a character on the display for a life indication
        debug_char = "v" if debug_char == "o" else "o"
        display.text(debug_char, 300, 225, 319, 0.9)
        
        display.update()
