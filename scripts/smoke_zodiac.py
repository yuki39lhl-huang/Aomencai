from app.services.zodiac import number_to_zodiac, wave_color, zodiac_numbers

assert number_to_zodiac(1) == "马"
assert number_to_zodiac(21) == "狗"
assert number_to_zodiac(49) == "马"
assert wave_color(21) == "绿波"
assert 49 in zodiac_numbers("马")
print("zodiac ok", zodiac_numbers("狗"))
