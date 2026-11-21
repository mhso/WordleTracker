import numpy as np
import cv2
from cv2.typing import MatLike

DEBUG = True

GREEN = np.array([78, 141, 83])
YELLOW = np.array([159, 59, 181])
GRAY = np.array([60, 58, 58])
BLACK = np.array([19, 18, 18])

SIFT_FLANN_INDEX_KDTREE = 0
SIFT_INDEX_PARAMS = dict(algorithm=SIFT_FLANN_INDEX_KDTREE, trees=5)
SIFT_SEARCH_PARAMS = dict(checks=50)

def within_range(color: np.ndarray, target: np.ndarray, threshold: int = 5):
    return (color > (target - threshold)).all() and (color < (target + threshold)).all()

def find_first_square(image: MatLike):
    h, w = image.shape[:2]
    step_size = 5

    for y in range(0, h, step_size):
        for x in range(0, w, step_size):
            if any(within_range(image[y, x], target) for target in (GREEN, YELLOW, GRAY)):
                return x, y

    return None

def find_next_square(image: MatLike, x: int, y: int, horizontal=True):
    color = image[y, x]

    coord = x if horizontal else y

    for i in range(coord, coord + 30):
        new_color = image[y if horizontal else i, i if horizontal else x]
        if (np.abs(new_color - color) > 5).all():
            return min(i + 5, image.shape[1 if horizontal else 0] - 1)

    return None

def is_contained(hierarchy, child, parent):
    while hierarchy[child][3] != -1:
        parent_id = hierarchy[child][3]
        if parent_id == parent:
            return True

        child = parent_id

    return False

def match_avatar(avatar_features, image):
    sift = cv2.SIFT.create()

    descriptors = sift.detectAndCompute(image, None)[1]
    flann = cv2.FlannBasedMatcher(SIFT_INDEX_PARAMS, SIFT_SEARCH_PARAMS)

    closest_match_id = None
    closest_match_val = 0
    for disc_id, features in avatar_features:
        matches = flann.knnMatch(descriptors, features, k=2)

        similarity = 0
        for m, n in matches:
            if m.distance < 0.7*n.distance:
                similarity += n.distance - m.distance

        similarity = similarity / len(matches) if len(matches) > 0 else 0

        if similarity > closest_match_val:
            closest_match_val = similarity
            closest_match_id = disc_id

    return closest_match_id

def determine_player_boxes(image: MatLike, avatar_images:  list[tuple[int, MatLike | None]]):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 40, 65, cv2.THRESH_BINARY)[1]
    kernel = np.ones((3, 3), np.uint8)

    thresh = cv2.morphologyEx(thresh, cv2.MORPH_DILATE, kernel)

    raw_contours, hierarchy = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    if raw_contours == []:
        raise RuntimeError("Could not find player contours!")

    raw_contours = list(enumerate(raw_contours))

    contours = [(i, c, cv2.contourArea(c)) for i, c in raw_contours]
    contours.sort(key=lambda t: t[2], reverse=True)

    box_contours = [contours[0]]
    prev_area = contours[0][2]
    for i, contour, area in contours[1:]:
        if prev_area - area > 500:
            break

        box_contours.append((i, contour, area))

        prev_area = area

    start_index = len(box_contours) * 3
    avatar_contours = contours[start_index:start_index + len(box_contours)]

    # Calculate sift features for avatars
    sift = cv2.SIFT.create()
    descriptors = [
        (disc_id, sift.detectAndCompute(avatar, None)[1] if avatar is not None else None)
        for disc_id, avatar in avatar_images
    ]

    player_boxes = []
    missing_disc_ids = []
    for i, contour, _ in box_contours:
        for j, other_contour, _ in avatar_contours:
            if is_contained(hierarchy[0], j, i):
                box = cv2.boundingRect(other_contour)
                roi = image[box[1]: box[1] + box[3], box[0]: box[0] + box[2], :]

                disc_id = match_avatar(descriptors, roi)
                bbox = cv2.boundingRect(contour)

                if disc_id is None:
                    missing_disc_ids.append(bbox)
                else:
                    player_boxes.append((disc_id, cv2.boundingRect(contour)))

                break

    if len(missing_disc_ids) > 1:
        raise ValueError("ERROR! More than one disc_id is missing!")
    elif missing_disc_ids: # Mads' avatar is the only one that was missing in the past
        player_boxes.append((331082926475182081, missing_disc_ids[0]))

    # for disc_id, box in player_boxes:
    #     x1, x2 = box[0], box[0] + box[2]
    #     y1, y2 = box[1], box[1] + box[3]

    #     cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 2)
    #     cv2.imshow("Test", image)
    #     cv2.waitKey(0)

    return player_boxes

def extract_wordle_scores(image: str | MatLike | bytes, user_avatars: list[tuple[int, str | None]]):
    """
    Extract Wordle scores from the given image with the given reference user avatars.
    For each entry, the score is:
      - None if the player is not finished
      - -1 if the player didn't guess the word
      - The number of guesses, otherwise
    """
    if isinstance(image, str):
        image = cv2.imread(image, cv2.IMREAD_COLOR)

    if isinstance(image, bytes):
        arr = np.frombuffer(image, np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if DEBUG:
        cv2.imwrite("image.png", image)

    avatar_images = [
        (disc_id, cv2.imread(path, cv2.IMREAD_COLOR))
        for disc_id, path in user_avatars
        if path
    ]
    player_boxes = determine_player_boxes(image, avatar_images)

    scores = []
    for disc_id, bbox in player_boxes:
        if len(player_boxes) == 1:
            y1 = bbox[1] + 10
            y2 = bbox[1] + bbox[3] - 10
            x1 = bbox[0] + (bbox[2] // 2)
            x2 = bbox[0] + bbox[2] - 10
            start_x, y = (20, 20)
        else:
            y1 = int(bbox[1] + bbox[3] * 0.5)
            y2 = bbox[1] + bbox[3] - 10
            x1 = bbox[0] + 10
            x2 = bbox[0] + bbox[2] - 10
            start_x, y = (10, 5)

        roi = image[y1:y2, x1:x2, :]

        if DEBUG:
            cv2.imwrite("image.png", image)
            copy = roi.copy()
            cv2.circle(copy, (start_x, y), 5, (0, 0, 255), 2)
            cv2.imwrite("start.png", copy)

        colors = []

        row = 0
        while row < 6:
            row_colors = []
            col = 0
            x = start_x
            while col < 5:
                row_colors.append(roi[y, x])
                x = find_next_square(roi, x, y, True)
                col += 1

            colors.append(row_colors)
            y = find_next_square(roi, start_x, y, False)
            row += 1

        score = -1
        for index, row in enumerate(colors):
            if all(within_range(color, GREEN) for color in row):
                score = index + 1
                break

            if all(within_range(color, BLACK) for color in row):
                score = None
                break

        scores.append((disc_id, score))

    return scores

def test():
    image = cv2.imread("test_data/test_5.png")

    avatars = [
        (115142485579137029, "test_data/avatar_dave.png"),
        (172757468814770176, "test_data/avatar_murt.png"),
        (267401734513491969, "test_data/avatar_gual.png"),
        (331082926475182081, "test_data/avatar_muds.png"),
        (347489125877809155, "test_data/avatar_no.png"),
    ]

    scores = extract_wordle_scores(image, avatars)
    print(scores)

