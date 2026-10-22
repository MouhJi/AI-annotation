"""Validation and geometry helpers for single-component instance polygons."""
from fastapi import HTTPException

def _area(points):
    return sum(x1*y2-x2*y1 for (x1,y1),(x2,y2) in zip(points, points[1:]+points[:1])) / 2

EPSILON = 1e-9
def _cross(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def _on_segment(a, b, c):
    return min(a[0], c[0])-EPSILON <= b[0] <= max(a[0], c[0])+EPSILON and min(a[1], c[1])-EPSILON <= b[1] <= max(a[1], c[1])+EPSILON
def _segments_cross(a,b,c,d):
    """Return true only when two finite segments meet, including an overlap.

    The previous sign-product test marked any two collinear lines as intersecting,
    even when they were separated. Segmentation masks commonly contain such edges.
    """
    one, two, three, four = _cross(a,b,c), _cross(a,b,d), _cross(c,d,a), _cross(c,d,b)
    if ((one > EPSILON and two < -EPSILON) or (one < -EPSILON and two > EPSILON)) and ((three > EPSILON and four < -EPSILON) or (three < -EPSILON and four > EPSILON)):
        return True
    return (abs(one) <= EPSILON and _on_segment(a,c,b)) or (abs(two) <= EPSILON and _on_segment(a,d,b)) or (abs(three) <= EPSILON and _on_segment(c,a,d)) or (abs(four) <= EPSILON and _on_segment(c,b,d))

def validate_polygon(points, image_width: int, image_height: int):
    if len(points) < 3: raise HTTPException(400, "Polygon needs at least three points")
    normalized=[(float(x),float(y)) for x,y in points]
    # A double-click in an editor can yield a duplicate final point. It is not a
    # self-intersection, so normalize repeated consecutive/closing points first.
    cleaned=[]
    for point in normalized:
        if not cleaned or abs(point[0]-cleaned[-1][0]) > 1e-6 or abs(point[1]-cleaned[-1][1]) > 1e-6:
            cleaned.append(point)
    if len(cleaned) > 1 and abs(cleaned[0][0]-cleaned[-1][0]) <= 1e-6 and abs(cleaned[0][1]-cleaned[-1][1]) <= 1e-6:
        cleaned.pop()
    normalized=cleaned
    if len(normalized) < 3: raise HTTPException(400, "Polygon needs at least three distinct points")
    if len({(round(x,6),round(y,6)) for x,y in normalized}) < 3: raise HTTPException(400,"Polygon needs three distinct points")
    if any(x<0 or y<0 or x>image_width or y>image_height for x,y in normalized): raise HTTPException(400,"Polygon points must be inside image dimensions")
    count=len(normalized)
    for i in range(count):
        for j in range(i+1,count):
            if j in {i,(i+1)%count} or (i==0 and j==count-1): continue
            if _segments_cross(normalized[i],normalized[(i+1)%count],normalized[j],normalized[(j+1)%count]): raise HTTPException(400,"Polygon must not self-intersect")
    if abs(_area(normalized)) < 1e-6: raise HTTPException(400,"Polygon area must be greater than zero")
    return normalized

def polygon_bbox(points):
    xs=[p[0] for p in points]; ys=[p[1] for p in points]
    return {"x":min(xs),"y":min(ys),"width":max(xs)-min(xs),"height":max(ys)-min(ys)}
