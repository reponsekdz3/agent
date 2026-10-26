def color_name(bgr_tuple: tuple[int, int, int]) -> str:
    b, g, r = bgr_tuple
    hsv = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0, 0]
    h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])
    if v < 45:
        return "black"
    if s < 35:
        return "white" if v > 180 else "gray"
    if h < 12 or h >= 168:
        return "red"
    if h < 22:
        return "orange"
    if h < 38:
        return "yellow"
    if h < 85:
        return "green"
    if h < 130:
        return "blue"
    return "purple"

print(v)