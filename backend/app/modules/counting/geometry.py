"""Hình học polygon chuẩn hoá cho cấu hình và đếm điểm neo vật thể."""

import math

Point = tuple[float, float]
EPSILON = 1e-9


# --------------------------- Tích có hướng ba điểm ---------------------------
def cross(a: Point, b: Point, c: Point) -> float:
    """Trả tích có hướng AB/AC để kiểm tra vị trí tương đối của ba điểm."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


# --------------------------- Điểm thuộc đoạn thẳng ---------------------------
def on_segment(point: Point, a: Point, b: Point) -> bool:
    """Trả True khi điểm nằm trên đoạn AB, kể cả hai đầu mút với sai số nhỏ."""
    return abs(cross(a, b, point)) <= EPSILON and all(
        min(a[i], b[i]) - EPSILON <= point[i] <= max(a[i], b[i]) + EPSILON
        for i in (0, 1)
    )


# ------------------------------- Giao hai đoạn -------------------------------
def intersects(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Kiểm tra hai đoạn giao hoặc chạm nhau; không thay đổi các điểm đầu vào."""
    ab_c, ab_d, cd_a, cd_b = (
        cross(a, b, c),
        cross(a, b, d),
        cross(c, d, a),
        cross(c, d, b),
    )
    if (
        (ab_c > EPSILON and ab_d < -EPSILON) or (ab_c < -EPSILON and ab_d > EPSILON)
    ) and (
        (cd_a > EPSILON and cd_b < -EPSILON) or (cd_a < -EPSILON and cd_b > EPSILON)
    ):
        return True
    return (
        on_segment(c, a, b)
        or on_segment(d, a, b)
        or on_segment(a, c, d)
        or on_segment(b, c, d)
    )


# ------------------------------ Polygon hợp lệ -------------------------------
def valid_polygon(points: list[Point]) -> bool:
    """Từ chối polygon trùng đỉnh, diện tích bằng không hoặc tự cắt, kể cả chạm cạnh."""
    if len(set(points)) != len(points):
        return False
    n = len(points)
    area = sum(
        points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1]
        for i in range(n)
    )
    if abs(area) < 1e-6:
        return False
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if intersects(a, b, points[j], points[(j + 1) % n]):
                return False
        # Cạnh kề không được gập ngược lên nhau.
        c = points[(i + 2) % n]
        if abs(cross(a, b, c)) <= EPSILON and (
            on_segment(c, a, b) or on_segment(a, b, c)
        ):
            return False
    return True


# ---------------------------- Điểm trong polygon -----------------------------
def contains(points: list[Point], point: Point) -> bool:
    """Ray casting cho polygon lõm/lồi; điểm nằm trên biên được tính là ở trong."""
    if not all(math.isfinite(value) for value in point):
        return False
    inside = False
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        if on_segment(point, a, b):
            return True
        if (a[1] > point[1]) != (b[1] > point[1]):
            x = (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]
            if point[0] < x:
                inside = not inside
    return inside
