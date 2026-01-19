"""
Via Stitcher KiCad Plugin - Automated via stitching and fencing using the IPC API.

Features:
- Zone-aware via placement (respects filled zone polygons)
- All-layer clearance checking (including internal layers)
- Via fencing around zone perimeters
- Multiple net support
- Selection-based stitching
- Random offset option
- Delete existing stitching vias
"""

import sys
import os
import math
import random
import logging
import traceback
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Sequence, Set, Dict, Any
from enum import Enum

# Setup logging to file and console EARLY - before any other imports that might fail
log_file = os.path.join(os.path.expanduser('~'), 'via_stitcher.log')

# Create a custom handler setup to ensure we always log
_file_handler = logging.FileHandler(log_file, mode='a')  # Append mode to preserve logs across runs
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.DEBUG)
_console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Get root logger and our module logger
logging.root.setLevel(logging.DEBUG)
logger = logging.getLogger('via_stitcher')
logger.setLevel(logging.DEBUG)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)
logger.propagate = False  # Don't double-log to root

logger.info("=" * 60)
logger.info("Via Stitcher plugin module loading...")
logger.info(f"Log file: {log_file}")
logger.info(f"Python version: {sys.version}")
logger.info(f"Python executable: {sys.executable}")
logger.info(f"Working directory: {os.getcwd()}")

# Flush handlers to ensure logs are written immediately
for handler in logger.handlers:
    handler.flush()

# Add plugin directory to path for relative imports
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)
logger.info(f"Plugin directory: {_plugin_dir}")
logger.info(f"sys.path: {sys.path[:5]}...")  # Log first 5 entries

# Import wx with error handling
try:
    logger.info("Importing wx...")
    import wx
    logger.info(f"wx imported successfully: {wx.version()}")
except Exception as e:
    logger.error(f"Failed to import wx: {e}")
    logger.error(traceback.format_exc())
    raise

# Import kipy modules with error handling
try:
    logger.info("Importing kipy modules...")
    from kipy import KiCad
    from kipy.board import Board as KipyBoard
    from kipy.board_types import (
        BoardLayer, Via, Zone, Track, ArcTrack, Pad,
        FootprintInstance, ViaType, Net, BoardRectangle, BoardSegment, BoardArc, BoardCircle
    )
    from kipy.geometry import Vector2
    from kipy.util import from_mm, to_mm
    logger.info("kipy modules imported successfully")
except Exception as e:
    logger.error(f"Failed to import kipy modules: {e}")
    logger.error(traceback.format_exc())
    raise

# Import our GUI module
try:
    logger.info("Importing ViaStitcherDialog...")
    from ui.via_stitcher_gui import ViaStitcherDialog
    logger.info("ViaStitcherDialog imported successfully")
except Exception as e:
    logger.error(f"Failed to import ViaStitcherDialog: {e}")
    logger.error(traceback.format_exc())
    raise

logger.info("All imports completed successfully")


class StitchMode(Enum):
    FILL = "fill"  # Fill zones with grid pattern
    FENCE_ZONE = "fence_zone"  # Place vias around zone perimeter
    FENCE_TRACE = "fence_trace"  # Place vias along selected traces (shielding)


@dataclass
class StitchingConfig:
    """Configuration for via stitching."""
    net_names: List[str] = field(default_factory=lambda: ["GND"])
    via_diameter_nm: int = from_mm(0.6)
    via_drill_nm: int = from_mm(0.3)
    grid_spacing_nm: int = from_mm(2.0)
    stagger_rows: bool = True
    clearance_nm: int = from_mm(0.2)
    boundary_clearance_nm: int = from_mm(0.3)
    random_offset: bool = False
    random_offset_max_nm: int = from_mm(0.2)
    mode: StitchMode = StitchMode.FILL
    fence_spacing_nm: int = from_mm(1.0)  # Spacing between fence vias
    fence_offset_nm: int = from_mm(0.5)  # Offset distance from trace for trace fencing
    fence_both_sides: bool = True  # Place vias on both sides of trace
    selected_only: bool = False
    via_type: ViaType = ViaType.VT_THROUGH
    # Layer settings for blind/buried vias
    start_layer: Optional[BoardLayer] = None
    end_layer: Optional[BoardLayer] = None
    # Board corner radius (IPC API doesn't expose this yet, so user must set it)
    board_corner_radius_nm: int = from_mm(0.0)


@dataclass
class StitchingResult:
    """Result of via stitching calculation."""
    zones_found: int = 0
    tracks_found: int = 0
    candidates: int = 0
    valid: int = 0
    rejected: int = 0
    rejected_reasons: dict = field(default_factory=dict)
    vias: List[Via] = field(default_factory=list)


def point_in_polygon(x: int, y: int, polygon_pts: List[Tuple[int, int]]) -> bool:
    """Check if a point is inside a polygon using ray casting."""
    if not polygon_pts or len(polygon_pts) < 3:
        return False
    inside = False
    n = len(polygon_pts)
    j = n - 1
    for i in range(n):
        xi, yi = polygon_pts[i]
        xj, yj = polygon_pts[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) // (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def point_to_segment_distance_sq(px: int, py: int, x1: int, y1: int, x2: int, y2: int) -> int:
    """Calculate squared distance from a point to a line segment."""
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return (px - x1) ** 2 + (py - y1) ** 2
    t = ((px - x1) * dx + (py - y1) * dy) / length_sq
    t = max(0, min(1, t))
    closest_x = x1 + int(t * dx)
    closest_y = y1 + int(t * dy)
    return (px - closest_x) ** 2 + (py - closest_y) ** 2


def distance_to_polygon_edge(x: int, y: int, polygon_pts: List[Tuple[int, int]]) -> float:
    """Calculate the minimum distance from a point to any edge of a polygon."""
    if not polygon_pts:
        return float('inf')
    min_dist_sq = float('inf')
    n = len(polygon_pts)
    for i in range(n):
        x1, y1 = polygon_pts[i]
        x2, y2 = polygon_pts[(i + 1) % n]
        dist_sq = point_to_segment_distance_sq(x, y, x1, y1, x2, y2)
        min_dist_sq = min(min_dist_sq, dist_sq)
    return math.sqrt(min_dist_sq)


def get_zone_polygon_pts(zone: Zone) -> List[Tuple[int, int]]:
    """Extract polygon points from a zone outline."""
    pts = []
    if zone.outline and zone.outline.outline:
        for node in zone.outline.outline.nodes:
            pts.append((node.point.x, node.point.y))
    return pts


def get_zone_filled_polygons(zone: Zone) -> List[List[Tuple[int, int]]]:
    """Extract filled polygon points from a zone (the actual copper areas)."""
    polygons = []
    # Try to get filled polygons if available
    if hasattr(zone, 'filled_polygons') and zone.filled_polygons:
        for filled_poly in zone.filled_polygons:
            # filled_poly has layer and shapes attributes
            if hasattr(filled_poly, 'shapes') and filled_poly.shapes:
                shapes = filled_poly.shapes
                # shapes has outlines attribute
                if hasattr(shapes, 'outlines') and shapes.outlines:
                    for outline in shapes.outlines:
                        if hasattr(outline, 'nodes') and outline.nodes:
                            pts = [(node.point.x, node.point.y) for node in outline.nodes]
                            if pts:
                                polygons.append(pts)
    # Fall back to outline if no filled polygons
    if not polygons:
        outline_pts = get_zone_polygon_pts(zone)
        if outline_pts:
            polygons.append(outline_pts)
    return polygons


def get_zone_layers(zone: Zone) -> List[BoardLayer]:
    """Get all layers a zone is on."""
    layers = []
    if hasattr(zone, 'layers') and zone.layers:
        layers = list(zone.layers)
    elif hasattr(zone, 'layer'):
        layers = [zone.layer]
    return layers


def get_board_outline(board: KipyBoard, corner_radius: int = 0) -> List[Tuple[int, int]]:
    """Extract board outline from Edge.Cuts shapes.

    Args:
        board: The KiCad board
        corner_radius: Corner radius in nm for rounded rectangles (IPC API doesn't expose this yet)
    """
    shapes = board.get_shapes()
    edge_cuts_layer = BoardLayer.BL_Edge_Cuts
    outline_pts = []
    for shape in shapes:
        if shape.layer != edge_cuts_layer:
            continue
        if isinstance(shape, BoardRectangle):
            tl = shape.top_left
            br = shape.bottom_right

            if corner_radius > 0:
                # Generate rounded rectangle outline with arc approximation
                # Corner centers are inset by corner_radius from each corner
                r = corner_radius
                x1, y1 = tl.x, tl.y  # top-left
                x2, y2 = br.x, br.y  # bottom-right

                # Generate points around the rounded rectangle
                # Top edge (left to right)
                outline_pts.append((x1 + r, y1))
                outline_pts.append((x2 - r, y1))
                # Top-right corner arc
                for i in range(8):
                    angle = -math.pi/2 + (math.pi/2) * i / 8
                    cx, cy = x2 - r, y1 + r
                    outline_pts.append((int(cx + r * math.cos(angle)), int(cy + r * math.sin(angle))))
                # Right edge (top to bottom)
                outline_pts.append((x2, y1 + r))
                outline_pts.append((x2, y2 - r))
                # Bottom-right corner arc
                for i in range(8):
                    angle = 0 + (math.pi/2) * i / 8
                    cx, cy = x2 - r, y2 - r
                    outline_pts.append((int(cx + r * math.cos(angle)), int(cy + r * math.sin(angle))))
                # Bottom edge (right to left)
                outline_pts.append((x2 - r, y2))
                outline_pts.append((x1 + r, y2))
                # Bottom-left corner arc
                for i in range(8):
                    angle = math.pi/2 + (math.pi/2) * i / 8
                    cx, cy = x1 + r, y2 - r
                    outline_pts.append((int(cx + r * math.cos(angle)), int(cy + r * math.sin(angle))))
                # Left edge (bottom to top)
                outline_pts.append((x1, y2 - r))
                outline_pts.append((x1, y1 + r))
                # Top-left corner arc
                for i in range(8):
                    angle = math.pi + (math.pi/2) * i / 8
                    cx, cy = x1 + r, y1 + r
                    outline_pts.append((int(cx + r * math.cos(angle)), int(cy + r * math.sin(angle))))
            else:
                # Simple rectangle - 4 corners
                outline_pts.extend([(tl.x, tl.y), (br.x, tl.y), (br.x, br.y), (tl.x, br.y)])
        elif isinstance(shape, BoardSegment):
            outline_pts.append((shape.start.x, shape.start.y))
            outline_pts.append((shape.end.x, shape.end.y))
        elif isinstance(shape, BoardArc):
            outline_pts.append((shape.start.x, shape.start.y))
            outline_pts.append((shape.end.x, shape.end.y))
        elif isinstance(shape, BoardCircle):
            cx, cy = shape.center.x, shape.center.y
            # Calculate radius from center to radius_point
            rp = shape.radius_point
            r = math.sqrt((rp.x - cx) ** 2 + (rp.y - cy) ** 2)
            for i in range(32):
                angle = 2 * math.pi * i / 32
                outline_pts.append((cx + int(r * math.cos(angle)), cy + int(r * math.sin(angle))))
    return outline_pts


def get_all_copper_layers(board: KipyBoard) -> List[BoardLayer]:
    """Get copper layers actually used on the board."""
    # Start with standard outer layers
    layers = [BoardLayer.BL_F_Cu, BoardLayer.BL_B_Cu]

    # Check which internal layers have content by looking at tracks
    tracks = board.get_tracks()
    used_layers = set(layers)

    for track in tracks:
        if hasattr(track, 'layer') and track.layer:
            used_layers.add(track.layer)

    # Filter to only copper layers
    copper_layer_names = {'BL_F_Cu', 'BL_B_Cu'}
    for i in range(1, 31):
        copper_layer_names.add(f'BL_In{i}_Cu')

    result = []
    for layer in used_layers:
        layer_name = layer.name if hasattr(layer, 'name') else str(layer)
        # Check if it's a copper layer
        if any(copper in layer_name for copper in ['F_Cu', 'B_Cu', 'In']) and 'Cu' in layer_name:
            result.append(layer)

    return result if result else layers  # Fallback to outer layers if detection fails


def generate_grid_positions(min_x, min_y, max_x, max_y, config: StitchingConfig) -> List[Tuple[int, int]]:
    """Generate a grid of potential via positions."""
    positions = []
    spacing = config.grid_spacing_nm
    start_x = ((min_x + spacing - 1) // spacing) * spacing
    start_y = ((min_y + spacing - 1) // spacing) * spacing
    row = 0
    y = start_y
    while y <= max_y:
        row_offset = (spacing // 2) if (config.stagger_rows and row % 2 == 1) else 0
        x = start_x + row_offset
        while x <= max_x:
            final_x, final_y = x, y
            # Apply random offset if enabled
            if config.random_offset:
                max_offset = config.random_offset_max_nm
                final_x += random.randint(-max_offset, max_offset)
                final_y += random.randint(-max_offset, max_offset)
            positions.append((final_x, final_y))
            x += spacing
        y += spacing
        row += 1
    return positions


def generate_fence_positions(polygon_pts: List[Tuple[int, int]], spacing_nm: int) -> List[Tuple[int, int]]:
    """Generate via positions along the perimeter of a polygon (fence pattern)."""
    if not polygon_pts or len(polygon_pts) < 2:
        return []

    positions = []
    n = len(polygon_pts)

    for i in range(n):
        x1, y1 = polygon_pts[i]
        x2, y2 = polygon_pts[(i + 1) % n]

        # Calculate segment length
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx * dx + dy * dy)

        if length < spacing_nm:
            # Segment too short, just add midpoint
            positions.append(((x1 + x2) // 2, (y1 + y2) // 2))
        else:
            # Add vias along segment
            num_vias = int(length / spacing_nm)
            for j in range(num_vias):
                t = (j + 0.5) / num_vias  # Center vias in their segments
                px = int(x1 + t * dx)
                py = int(y1 + t * dy)
                positions.append((px, py))

    return positions


def chain_tracks_into_paths(tracks: List) -> List[List[Tuple[int, int]]]:
    """Chain connected track segments into continuous paths.

    Returns a list of paths, where each path is a list of (x, y) points.
    """
    if not tracks:
        return []

    # Build a list of segments as (start, end) tuples
    segments = []
    for track in tracks:
        if isinstance(track, ArcTrack):
            # For arcs, sample points along the arc
            center = track.center()
            radius = track.radius()
            if center and radius > 0:
                start_angle = track.start_angle() or 0
                arc_angle = track.angle() or math.pi
                # Determine direction
                mid_vec_x = track.mid.x - center.x
                mid_vec_y = track.mid.y - center.y
                mid_angle = math.atan2(mid_vec_y, mid_vec_x)

                def norm_angle(a):
                    while a < 0: a += 2 * math.pi
                    while a >= 2 * math.pi: a -= 2 * math.pi
                    return a

                diff = norm_angle(mid_angle) - norm_angle(start_angle)
                if diff > math.pi: diff -= 2 * math.pi
                elif diff < -math.pi: diff += 2 * math.pi
                direction = 1 if diff > 0 else -1

                # Sample arc into points
                num_samples = max(8, int(radius * arc_angle / from_mm(0.5)))  # ~0.5mm per sample
                arc_pts = []
                for i in range(num_samples + 1):
                    angle = start_angle + (arc_angle * i / num_samples) * direction
                    px = int(center.x + radius * math.cos(angle))
                    py = int(center.y + radius * math.sin(angle))
                    arc_pts.append((px, py))
                segments.append(arc_pts)
            else:
                # Degenerate arc
                segments.append([(track.start.x, track.start.y), (track.end.x, track.end.y)])
        else:
            segments.append([(track.start.x, track.start.y), (track.end.x, track.end.y)])

    # Now chain segments that share endpoints
    # Use a simple greedy approach
    paths = []
    used = [False] * len(segments)

    def points_close(p1, p2, tol=from_mm(0.01)):
        return abs(p1[0] - p2[0]) < tol and abs(p1[1] - p2[1]) < tol

    for i, seg in enumerate(segments):
        if used[i]:
            continue

        # Start a new path
        path = list(seg)
        used[i] = True

        # Try to extend in both directions
        changed = True
        while changed:
            changed = False
            for j, other_seg in enumerate(segments):
                if used[j]:
                    continue

                # Check if other_seg connects to start of path
                if points_close(other_seg[-1], path[0]):
                    path = list(other_seg[:-1]) + path
                    used[j] = True
                    changed = True
                elif points_close(other_seg[0], path[0]):
                    path = list(reversed(other_seg[1:])) + path
                    used[j] = True
                    changed = True
                # Check if other_seg connects to end of path
                elif points_close(other_seg[0], path[-1]):
                    path = path + list(other_seg[1:])
                    used[j] = True
                    changed = True
                elif points_close(other_seg[-1], path[-1]):
                    path = path + list(reversed(other_seg[:-1]))
                    used[j] = True
                    changed = True

        paths.append(path)

    return paths


def generate_offset_path(path: List[Tuple[int, int]], offset: int, side: int) -> List[Tuple[int, int]]:
    """Generate an offset (outset) path from the input path.

    Args:
        path: List of (x, y) points defining the centerline
        offset: Offset distance in nm
        side: 1 for left side, -1 for right side

    Returns:
        List of (x, y) points for the offset path
    """
    if len(path) < 2:
        return []

    offset_pts = []

    for i in range(len(path)):
        x, y = path[i]

        # Calculate the perpendicular direction at this point
        # Use average of incoming and outgoing segment directions for smooth corners

        if i == 0:
            # First point - use outgoing direction only
            dx = path[i + 1][0] - x
            dy = path[i + 1][1] - y
        elif i == len(path) - 1:
            # Last point - use incoming direction only
            dx = x - path[i - 1][0]
            dy = y - path[i - 1][1]
        else:
            # Middle point - average incoming and outgoing
            dx1 = x - path[i - 1][0]
            dy1 = y - path[i - 1][1]
            dx2 = path[i + 1][0] - x
            dy2 = path[i + 1][1] - y

            # Normalize both
            len1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
            len2 = math.sqrt(dx2 * dx2 + dy2 * dy2)

            if len1 > 0 and len2 > 0:
                dx = dx1 / len1 + dx2 / len2
                dy = dy1 / len1 + dy2 / len2
            elif len1 > 0:
                dx, dy = dx1, dy1
            else:
                dx, dy = dx2, dy2

        length = math.sqrt(dx * dx + dy * dy)
        if length == 0:
            continue

        # Perpendicular direction (rotate 90 degrees)
        px = -dy / length * side
        py = dx / length * side

        # Offset point
        ox = int(x + offset * px)
        oy = int(y + offset * py)
        offset_pts.append((ox, oy))

    return offset_pts


def sample_path_at_intervals(path: List[Tuple[int, int]], spacing: int) -> List[Tuple[int, int]]:
    """Sample points along a path at regular intervals.

    Args:
        path: List of (x, y) points
        spacing: Distance between samples in nm

    Returns:
        List of (x, y) sample points
    """
    if len(path) < 2:
        return list(path)

    samples = [path[0]]
    accumulated_dist = 0

    for i in range(1, len(path)):
        x1, y1 = path[i - 1]
        x2, y2 = path[i]

        dx = x2 - x1
        dy = y2 - y1
        seg_len = math.sqrt(dx * dx + dy * dy)

        if seg_len == 0:
            continue

        # Walk along this segment
        remaining = spacing - accumulated_dist
        pos = remaining

        while pos <= seg_len:
            t = pos / seg_len
            sx = int(x1 + t * dx)
            sy = int(y1 + t * dy)
            samples.append((sx, sy))
            pos += spacing

        # Update accumulated distance for next segment
        accumulated_dist = (accumulated_dist + seg_len) % spacing

    # Always include the last point
    if samples[-1] != path[-1]:
        samples.append(path[-1])

    return samples


def generate_path_fence_positions(tracks: List, spacing_nm: int, offset_nm: int,
                                   both_sides: bool = True) -> List[Tuple[int, int]]:
    """Generate via positions by creating offset paths and sampling at regular intervals.

    This creates smooth fence via placement that follows the trace path properly,
    with even spacing around corners.
    """
    # Chain tracks into continuous paths
    paths = chain_tracks_into_paths(tracks)
    logger.debug(f"Chained {len(tracks)} tracks into {len(paths)} paths")

    positions = []
    sides = [1, -1] if both_sides else [1]

    for path in paths:
        if len(path) < 2:
            continue

        for side in sides:
            # Generate offset path (outset)
            offset_path = generate_offset_path(path, offset_nm, side)

            if len(offset_path) < 2:
                continue

            # Sample at regular intervals
            sampled = sample_path_at_intervals(offset_path, spacing_nm)
            positions.extend(sampled)

    return positions


def get_selected_tracks(board: KipyBoard) -> List:
    """Get currently selected tracks from the board."""
    selection = board.get_selection()
    selected = []
    for item in selection:
        if isinstance(item, (Track, ArcTrack)):
            selected.append(item)
    return selected


def check_clearance_to_pads(x: int, y: int, via_radius: int, pads: Sequence[Pad],
                            target_nets: Set[str], clearance: int) -> Tuple[bool, str]:
    """Check clearance to all pads on all layers."""
    for pad in pads:
        pad_x, pad_y = pad.position.x, pad.position.y
        dx_abs = abs(x - pad_x)
        dy_abs = abs(y - pad_y)

        copper_layers = pad.padstack.copper_layers if pad.padstack else []
        if not copper_layers:
            continue

        # Get the LARGEST pad size across all copper layers
        # (mounting holes have multiple pads with different sizes)
        pad_half_w = 0
        pad_half_h = 0
        for layer in copper_layers:
            layer_half_w = layer.size.x // 2
            layer_half_h = layer.size.y // 2
            pad_half_w = max(pad_half_w, layer_half_w)
            pad_half_h = max(pad_half_h, layer_half_h)

        pad_net = pad.net.name if pad.net else ""

        # Different clearance for same net vs different net
        # BUT: Don't reduce clearance for large pads (mounting holes) - can't place via inside a hole!
        # Consider a pad "large" if either dimension > 5mm (typical mounting holes are 6mm+)
        is_mounting_hole = pad_half_w > from_mm(2.5) or pad_half_h > from_mm(2.5)
        if pad_net in target_nets and not is_mounting_hole:
            req_clearance = clearance // 2
        else:
            req_clearance = clearance

        if dx_abs < via_radius + pad_half_w + req_clearance and dy_abs < via_radius + pad_half_h + req_clearance:
            return False, f"pad ({pad_net})"
    return True, ""


def check_clearance_to_vias(x: int, y: int, via_radius: int, vias: Sequence[Via],
                            target_nets: Set[str], clearance: int, same_net_clearance: int) -> Tuple[bool, str]:
    """Check clearance to existing vias."""
    # Pre-compute max distance for quick filtering
    max_check_dist = via_radius + clearance + from_mm(1.5)  # 1.5mm for typical via

    for via in vias:
        via_x, via_y = via.position.x, via.position.y

        # Quick distance check first
        dx = x - via_x
        dy = y - via_y
        if abs(dx) > max_check_dist or abs(dy) > max_check_dist:
            continue

        existing_radius = via.diameter // 2
        dist_sq = dx * dx + dy * dy
        via_net = via.net.name if via.net else ""
        min_dist = via_radius + existing_radius + (same_net_clearance if via_net in target_nets else clearance)
        if dist_sq < min_dist * min_dist:
            return False, f"via ({via_net})"
    return True, ""


def check_clearance_to_tracks(x: int, y: int, via_radius: int, tracks: Sequence,
                               target_nets: Set[str], clearance: int, same_net_clearance: int,
                               layers: List[BoardLayer]) -> Tuple[bool, str]:
    """Check clearance to tracks on specified layers."""
    # Pre-compute max distance to check (used for bounding box filtering)
    max_check_dist = via_radius + clearance + from_mm(1.0)  # Add 1mm for track width

    for track in tracks:
        # Quick bounding box check first
        if isinstance(track, ArcTrack):
            # Use arc start/mid/end for bounding
            pts = [track.start, track.mid, track.end]
            min_tx = min(p.x for p in pts)
            max_tx = max(p.x for p in pts)
            min_ty = min(p.y for p in pts)
            max_ty = max(p.y for p in pts)
        else:
            min_tx = min(track.start.x, track.end.x)
            max_tx = max(track.start.x, track.end.x)
            min_ty = min(track.start.y, track.end.y)
            max_ty = max(track.start.y, track.end.y)

        # Skip if point is clearly outside track bounding box
        if x < min_tx - max_check_dist or x > max_tx + max_check_dist:
            continue
        if y < min_ty - max_check_dist or y > max_ty + max_check_dist:
            continue

        # Check if track is on any of the relevant layers
        track_layer = track.layer if hasattr(track, 'layer') else None
        if track_layer not in layers and track_layer != BoardLayer.BL_UNKNOWN:
            continue

        track_width_half = track.width // 2
        track_net = track.net.name if track.net else ""
        req_clearance = same_net_clearance if track_net in target_nets else clearance
        min_dist = via_radius + track_width_half + req_clearance

        # Handle both Track and ArcTrack
        if isinstance(track, ArcTrack):
            # For arc tracks, check distance to start, mid, and end points as approximation
            for pt in [track.start, track.mid, track.end]:
                dx, dy = x - pt.x, y - pt.y
                dist_sq = dx * dx + dy * dy
                if dist_sq < min_dist * min_dist:
                    return False, f"arc ({track_net})"
        else:
            dist_sq = point_to_segment_distance_sq(x, y, track.start.x, track.start.y,
                                                    track.end.x, track.end.y)
            if dist_sq < min_dist * min_dist:
                return False, f"track ({track_net})"
    return True, ""


def check_clearance_to_zones(x: int, y: int, via_radius: int, zones: Sequence[Zone],
                              target_nets: Set[str], clearance: int) -> Tuple[bool, str]:
    """Check clearance to zones that are NOT in our target nets.

    Note: We intentionally do NOT reject vias inside other zones.
    Zones are "soft" - they will refill with clearance around the via.
    This matches Altium behavior. DRC will catch any real violations.
    """
    # Don't check zone overlaps - zones refill around vias automatically
    # Only tracks, pads, and existing vias are "hard" obstacles
    return True, ""


def get_selected_zones(board: KipyBoard) -> List[Zone]:
    """Get currently selected zones from the board."""
    selection = board.get_selection()
    selected = []
    for item in selection:
        if isinstance(item, Zone):
            selected.append(item)
    return selected


# ============ Parallel Processing Support ============

@dataclass
class BoardData:
    """Picklable board data for parallel processing."""
    # Tracks: list of (start_x, start_y, end_x, end_y, width, net_name, layer_name, is_arc, mid_x, mid_y)
    tracks: List[Tuple]
    # Pads: list of (x, y, half_w, half_h, net_name)
    pads: List[Tuple]
    # Vias: list of (x, y, radius, net_name)
    vias: List[Tuple]
    # Zone polygons: list of (net_name, polygon_pts)
    zone_polygons: List[Tuple]
    # Board outline
    board_outline: List[Tuple[int, int]]
    # Copper layer names
    copper_layers: Set[str]


def extract_board_data(board: KipyBoard, corner_radius: int = 0) -> BoardData:
    """Extract board data into picklable structures for parallel processing.

    Args:
        board: The KiCad board
        corner_radius: Board corner radius in nm (for rounded rectangles)
    """
    logger.debug("Starting board data extraction...")

    # Extract tracks
    tracks_data = []
    logger.debug("Extracting tracks...")
    for track in board.get_tracks():
        layer_name = track.layer.name if hasattr(track.layer, 'name') else str(track.layer)
        net_name = track.net.name if track.net else ""
        is_arc = isinstance(track, ArcTrack)
        if is_arc:
            tracks_data.append((
                track.start.x, track.start.y,
                track.end.x, track.end.y,
                track.width, net_name, layer_name,
                True, track.mid.x, track.mid.y
            ))
        else:
            tracks_data.append((
                track.start.x, track.start.y,
                track.end.x, track.end.y,
                track.width, net_name, layer_name,
                False, 0, 0
            ))

    logger.debug(f"Extracted {len(tracks_data)} tracks")

    # Extract pads
    pads_data = []
    logger.debug("Extracting pads...")
    for pad in board.get_pads():
        copper_layers = pad.padstack.copper_layers if pad.padstack else []
        if not copper_layers:
            continue
        # Get the LARGEST pad size across all copper layers
        # (mounting holes have multiple pads with different sizes)
        pad_half_w = 0
        pad_half_h = 0
        for layer in copper_layers:
            layer_half_w = layer.size.x // 2
            layer_half_h = layer.size.y // 2
            pad_half_w = max(pad_half_w, layer_half_w)
            pad_half_h = max(pad_half_h, layer_half_h)
        pads_data.append((
            pad.position.x, pad.position.y,
            pad_half_w, pad_half_h,
            pad.net.name if pad.net else ""
        ))

    logger.debug(f"Extracted {len(pads_data)} pads")

    # Extract vias
    vias_data = []
    logger.debug("Extracting vias...")
    for via in board.get_vias():
        vias_data.append((
            via.position.x, via.position.y,
            via.diameter // 2,
            via.net.name if via.net else ""
        ))

    logger.debug(f"Extracted {len(vias_data)} vias")

    # Extract zone polygons
    zone_polygons_data = []
    logger.debug("Extracting zone polygons...")
    for zone in board.get_zones():
        net_name = zone.net.name if zone.net else ""
        for polygon_pts in get_zone_filled_polygons(zone):
            zone_polygons_data.append((net_name, polygon_pts))

    logger.debug(f"Extracted {len(zone_polygons_data)} zone polygons")

    # Get board outline and copper layers
    logger.debug(f"Getting board outline (corner_radius={to_mm(corner_radius):.2f}mm)...")
    board_outline = get_board_outline(board, corner_radius)
    logger.debug(f"Board outline has {len(board_outline)} points")

    logger.debug("Getting copper layers...")
    copper_layers = set()
    for layer in get_all_copper_layers(board):
        layer_name = layer.name if hasattr(layer, 'name') else str(layer)
        copper_layers.add(layer_name)
    logger.debug(f"Found {len(copper_layers)} copper layers: {copper_layers}")

    logger.debug("Board data extraction complete")
    return BoardData(
        tracks=tracks_data,
        pads=pads_data,
        vias=vias_data,
        zone_polygons=zone_polygons_data,
        board_outline=board_outline,
        copper_layers=copper_layers
    )


def check_position_parallel(args) -> Tuple[int, int, bool, str]:
    """Check a single position for clearance (for parallel processing).

    Returns: (x, y, is_valid, rejection_reason)
    """
    (x, y, via_radius, target_nets, clearance, same_net_clearance,
     boundary_clearance, board_data_dict, is_fence_mode, polygon_pts) = args

    tracks = board_data_dict['tracks']
    pads = board_data_dict['pads']
    vias = board_data_dict['vias']
    zone_polygons = board_data_dict['zone_polygons']
    board_outline = board_data_dict['board_outline']
    copper_layers = board_data_dict['copper_layers']

    # Check if point is inside board outline
    if board_outline and not point_in_polygon(x, y, board_outline):
        return (x, y, False, "outside_board")

    # Check board edge clearance (must account for via radius!)
    if board_outline:
        edge_dist = distance_to_polygon_edge(x, y, board_outline)
        min_edge_dist = boundary_clearance + via_radius
        if edge_dist < min_edge_dist:
            return (x, y, False, "board_edge")

    # Check zone boundary clearance (for fill mode only)
    if not is_fence_mode and polygon_pts:
        if distance_to_polygon_edge(x, y, polygon_pts) < boundary_clearance + via_radius:
            return (x, y, False, "zone_edge")

    # Check clearance to pads
    for pad_x, pad_y, pad_half_w, pad_half_h, pad_net in pads:
        dx_abs = abs(x - pad_x)
        dy_abs = abs(y - pad_y)

        # Quick filter based on actual pad size
        max_check_dist = via_radius + clearance + pad_half_w + pad_half_h
        if dx_abs > max_check_dist or dy_abs > max_check_dist:
            continue

        # Don't reduce clearance for large pads (mounting holes) - can't place via inside a hole!
        # Consider a pad "large" if either dimension > 5mm (2.5mm half-size)
        is_mounting_hole = pad_half_w > from_mm(2.5) or pad_half_h > from_mm(2.5)
        if pad_net in target_nets and not is_mounting_hole:
            req_clearance = clearance // 2
        else:
            req_clearance = clearance
        if dx_abs < via_radius + pad_half_w + req_clearance and dy_abs < via_radius + pad_half_h + req_clearance:
            return (x, y, False, "pad")

    # Check clearance to existing vias
    max_check_dist = via_radius + clearance + from_mm(1.5)
    for via_x, via_y, existing_radius, via_net in vias:
        dx = x - via_x
        dy = y - via_y
        if abs(dx) > max_check_dist or abs(dy) > max_check_dist:
            continue
        min_dist = via_radius + existing_radius + (same_net_clearance if via_net in target_nets else clearance)
        if dx * dx + dy * dy < min_dist * min_dist:
            return (x, y, False, "via")

    # Check clearance to tracks
    max_check_dist = via_radius + clearance + from_mm(1.0)
    for track_data in tracks:
        (start_x, start_y, end_x, end_y, width, track_net, layer_name,
         is_arc, mid_x, mid_y) = track_data

        # Layer check
        if layer_name not in copper_layers and 'UNKNOWN' not in layer_name:
            continue

        # Bounding box check
        if is_arc:
            min_tx = min(start_x, mid_x, end_x)
            max_tx = max(start_x, mid_x, end_x)
            min_ty = min(start_y, mid_y, end_y)
            max_ty = max(start_y, mid_y, end_y)
        else:
            min_tx = min(start_x, end_x)
            max_tx = max(start_x, end_x)
            min_ty = min(start_y, end_y)
            max_ty = max(start_y, end_y)

        if x < min_tx - max_check_dist or x > max_tx + max_check_dist:
            continue
        if y < min_ty - max_check_dist or y > max_ty + max_check_dist:
            continue

        track_width_half = width // 2
        req_clearance = same_net_clearance if track_net in target_nets else clearance
        min_dist = via_radius + track_width_half + req_clearance

        if is_arc:
            # Check distance to arc points
            for px, py in [(start_x, start_y), (mid_x, mid_y), (end_x, end_y)]:
                dx, dy = x - px, y - py
                if dx * dx + dy * dy < min_dist * min_dist:
                    return (x, y, False, "arc")
        else:
            dist_sq = point_to_segment_distance_sq(x, y, start_x, start_y, end_x, end_y)
            if dist_sq < min_dist * min_dist:
                return (x, y, False, "track")

    # Check rule area overlap
    # Rule areas are hard obstacles - vias should not be placed inside them
    # Zone polygons with empty net name are typically rule areas
    for zone_net, zone_poly in zone_polygons:
        if zone_net:  # Skip copper zones (they have net names)
            continue
        if not zone_poly or len(zone_poly) < 3:
            continue

        # Check if via center is inside the rule area
        if point_in_polygon(x, y, zone_poly):
            return (x, y, False, "rule_area")

        # Check if via circle edge overlaps with rule area
        dist_to_edge = distance_to_polygon_edge(x, y, zone_poly)
        if dist_to_edge < via_radius:
            return (x, y, False, "rule_area")

    # Note: Copper zones (with net names) are "soft" - they refill around vias.
    # This matches Altium behavior.

    return (x, y, True, "")


def check_positions_batch(positions: List[Tuple[int, int]], via_radius: int,
                          target_nets: Set[str], clearance: int, same_net_clearance: int,
                          boundary_clearance: int, board_data: BoardData,
                          is_fence_mode: bool = False,
                          polygon_pts: List[Tuple[int, int]] = None,
                          progress_callback=None) -> List[Tuple[int, int, bool, str]]:
    """Check multiple positions for clearance.

    Returns list of (x, y, is_valid, rejection_reason) tuples.
    """
    logger.debug(f"check_positions_batch: checking {len(positions)} positions")

    if not positions:
        return []

    # Convert board data to dict
    board_data_dict = {
        'tracks': board_data.tracks,
        'pads': board_data.pads,
        'vias': board_data.vias,
        'zone_polygons': board_data.zone_polygons,
        'board_outline': board_data.board_outline,
        'copper_layers': board_data.copper_layers,
    }

    results = []

    # Sequential processing (safe for GUI context)
    total = len(positions)
    for idx, (x, y) in enumerate(positions):
        # Update progress every 100 positions to keep GUI responsive
        if idx % 100 == 0:
            logger.debug(f"Checking position {idx}/{total}")
            if progress_callback:
                progress_callback(idx, total, f"Checking position {idx}/{total}")

        result = check_position_parallel((
            x, y, via_radius, target_nets, clearance, same_net_clearance,
            boundary_clearance, board_data_dict, is_fence_mode, polygon_pts
        ))
        results.append(result)

    logger.debug(f"check_positions_batch complete: {len(results)} results")
    return results


def generate_trace_fencing(board: KipyBoard, config: StitchingConfig,
                            selected_tracks: List = None,
                            progress_callback=None) -> StitchingResult:
    """Generate via fencing along traces for shielding."""
    result = StitchingResult()

    nets = board.get_nets()
    all_tracks = board.get_tracks()

    # Build set of target nets (for the fence vias, typically GND)
    target_nets = set(config.net_names)

    # Find net objects for target nets
    net_objects = {}
    for net in nets:
        if net.name in target_nets:
            net_objects[net.name] = net

    if not net_objects:
        result.rejected_reasons["no_nets"] = "No matching nets found for fence vias"
        return result

    # Use first target net for the fence vias
    fence_net = net_objects.get(config.net_names[0]) if config.net_names else None
    if not fence_net:
        result.rejected_reasons["no_fence_net"] = "No net found for fence vias"
        return result

    # Get tracks to fence - MUST be selected, never fall back to all tracks
    if selected_tracks is None or len(selected_tracks) == 0:
        result.rejected_reasons["no_tracks"] = "No tracks selected. Select the traces you want to fence in KiCad first."
        return result

    tracks_to_fence = selected_tracks
    result.tracks_found = len(tracks_to_fence)

    via_radius = config.via_diameter_nm // 2
    same_net_clearance = from_mm(0.127)

    if progress_callback:
        progress_callback(0, 1, "Extracting board data...")

    # Extract board data once for parallel processing
    board_data = extract_board_data(board, config.board_corner_radius_nm)

    # Generate fence positions using path-based outset approach
    if progress_callback:
        progress_callback(0, 1, "Generating fence positions...")

    all_positions = generate_path_fence_positions(
        tracks_to_fence, config.fence_spacing_nm, config.fence_offset_nm, config.fence_both_sides
    )

    logger.debug(f"Generated {len(all_positions)} fence positions from {len(tracks_to_fence)} tracks")
    result.candidates = len(all_positions)

    if progress_callback:
        progress_callback(0, 1, f"Checking {len(all_positions)} positions in parallel...")

    # Check all positions
    check_results = check_positions_batch(
        all_positions, via_radius, target_nets, config.clearance_nm,
        same_net_clearance, config.boundary_clearance_nm, board_data,
        is_fence_mode=True, polygon_pts=None, progress_callback=progress_callback
    )

    # Process results
    for x, y, is_valid, rejection_reason in check_results:
        if is_valid:
            via = Via()
            via.position = Vector2.from_xy(x, y)
            via.net = fence_net
            via.type = config.via_type
            via.diameter = config.via_diameter_nm
            via.drill_diameter = config.via_drill_nm
            if config.via_type != ViaType.VT_THROUGH:
                if config.start_layer:
                    via.start_layer = config.start_layer
                if config.end_layer:
                    via.end_layer = config.end_layer
            result.vias.append(via)
            result.valid += 1
        else:
            result.rejected += 1
            result.rejected_reasons[rejection_reason] = result.rejected_reasons.get(rejection_reason, 0) + 1

    return result


def generate_via_stitching(board: KipyBoard, config: StitchingConfig,
                           progress_callback=None, selected_zones: List[Zone] = None,
                           selected_tracks: List = None) -> StitchingResult:
    """Generate via stitching for the board."""
    logger.info(f"generate_via_stitching called with mode={config.mode}")

    # Handle trace fencing mode separately
    if config.mode == StitchMode.FENCE_TRACE:
        logger.info("Dispatching to trace fencing mode")
        return generate_trace_fencing(board, config, selected_tracks, progress_callback)

    result = StitchingResult()

    logger.debug("Getting zones and nets...")
    zones = board.get_zones()
    nets = board.get_nets()
    logger.debug(f"Found {len(zones)} zones and {len(nets)} nets")

    # Build set of target nets
    target_nets = set(config.net_names)

    # Find net objects for target nets
    net_objects = {}
    for net in nets:
        if net.name in target_nets:
            net_objects[net.name] = net

    if not net_objects:
        result.rejected_reasons["no_nets"] = "No matching nets found"
        return result

    # Find zones for target nets
    if config.selected_only and selected_zones:
        # Only use selected zones that match target nets
        target_zones = [z for z in selected_zones if z.net and z.net.name in target_nets]
    else:
        target_zones = [z for z in zones if z.net and z.net.name in target_nets]
    result.zones_found = len(target_zones)

    if not target_zones:
        result.rejected_reasons["no_zones"] = "No zones found for target nets"
        return result

    via_radius = config.via_diameter_nm // 2
    same_net_clearance = from_mm(0.127)  # Minimum same-net clearance

    if progress_callback:
        progress_callback(0, 1, "Extracting board data...")

    # Extract board data once for parallel processing
    board_data = extract_board_data(board, config.board_corner_radius_nm)

    is_fence_mode = config.mode == StitchMode.FENCE_ZONE

    total_zones = len(target_zones)

    for zone_idx, zone in enumerate(target_zones):
        if progress_callback:
            progress_callback(zone_idx, total_zones, f"Processing zone {zone_idx + 1}/{total_zones}")

        zone_net = zone.net.name if zone.net else ""
        target_net = net_objects.get(zone_net)
        if not target_net:
            continue

        # Get zone polygons (filled areas)
        polygons = get_zone_filled_polygons(zone)

        for polygon_pts in polygons:
            if not polygon_pts:
                continue

            if config.mode == StitchMode.FILL:
                # Grid fill mode
                all_x = [p[0] for p in polygon_pts]
                all_y = [p[1] for p in polygon_pts]
                min_x, max_x = min(all_x), max(all_x)
                min_y, max_y = min(all_y), max(all_y)

                grid_positions = generate_grid_positions(min_x, min_y, max_x, max_y, config)
                # Pre-filter: only keep positions inside polygon
                grid_positions = [(x, y) for x, y in grid_positions if point_in_polygon(x, y, polygon_pts)]
            else:
                # Zone fence mode - vias around perimeter
                grid_positions = generate_fence_positions(polygon_pts, config.fence_spacing_nm)

            result.candidates += len(grid_positions)

            if not grid_positions:
                continue

            # Check all positions
            check_results = check_positions_batch(
                grid_positions, via_radius, target_nets, config.clearance_nm,
                same_net_clearance, config.boundary_clearance_nm, board_data,
                is_fence_mode=is_fence_mode, polygon_pts=polygon_pts,
                progress_callback=progress_callback
            )

            # Process results
            for x, y, is_valid, rejection_reason in check_results:
                if is_valid:
                    via = Via()
                    via.position = Vector2.from_xy(x, y)
                    via.net = target_net
                    via.type = config.via_type
                    via.diameter = config.via_diameter_nm
                    via.drill_diameter = config.via_drill_nm
                    if config.via_type != ViaType.VT_THROUGH:
                        if config.start_layer:
                            via.start_layer = config.start_layer
                        if config.end_layer:
                            via.end_layer = config.end_layer
                    result.vias.append(via)
                    result.valid += 1
                else:
                    result.rejected += 1
                    result.rejected_reasons[rejection_reason] = result.rejected_reasons.get(rejection_reason, 0) + 1

    return result


def find_stitching_vias(board: KipyBoard, net_names: List[str],
                        via_diameter_nm: int, via_drill_nm: int) -> List[Via]:
    """Find existing stitching vias that match the criteria."""
    vias = board.get_vias()
    target_nets = set(net_names)

    matching_vias = []
    for via in vias:
        via_net = via.net.name if via.net else ""
        if via_net not in target_nets:
            continue
        # Match by size (within tolerance)
        if abs(via.diameter - via_diameter_nm) < from_mm(0.01) and \
           abs(via.drill_diameter - via_drill_nm) < from_mm(0.01):
            matching_vias.append(via)

    return matching_vias


class ViaStitcherApp(ViaStitcherDialog):
    """Main application class for via stitcher."""

    def __init__(self):
        logger.info("ViaStitcherApp.__init__ starting")
        self.kicad = KiCad()
        logger.debug("KiCad connection established")
        self.board = self.kicad.get_board()
        logger.debug("Board obtained")
        nets = [net.name for net in self.board.get_nets()]
        logger.debug(f"Found {len(nets)} nets")
        super().__init__(None, nets=nets)
        self.result = None
        logger.info("ViaStitcherApp.__init__ complete")

    def _get_stitch_mode(self, config_dict):
        """Get stitch mode from config dict."""
        fence_mode = config_dict.get('fence_mode', '')
        if fence_mode == 'zone':
            return StitchMode.FENCE_ZONE
        elif fence_mode == 'trace':
            return StitchMode.FENCE_TRACE
        else:
            return StitchMode.FILL

    def on_preview(self, event):
        logger.info("on_preview started")
        try:
            self.update_status(message="Calculating...")
            app = wx.GetApp()
            if app:
                app.Yield()

            logger.debug("Getting config...")
            config_dict = self.get_config()
            logger.debug(f"Config: net={config_dict.get('net_name')}, fence_mode={config_dict.get('fence_mode')}")

            # Build net list
            net_names = [config_dict['net_name']]
            if config_dict.get('additional_nets'):
                net_names.extend(config_dict['additional_nets'])

            # Map via type string to ViaType enum
            via_type_map = {
                'Through': ViaType.VT_THROUGH,
                'Blind/Buried': ViaType.VT_BLIND_BURIED,
                'Micro': ViaType.VT_MICRO,
            }
            via_type_str = config_dict.get('via_type', 'Through')
            via_type = via_type_map.get(via_type_str, ViaType.VT_THROUGH)

            # Map layer strings to BoardLayer
            start_layer = None
            end_layer = None
            if via_type != ViaType.VT_THROUGH:
                start_layer_str = config_dict.get('start_layer', 'F.Cu')
                end_layer_str = config_dict.get('end_layer', 'B.Cu')
                layer_map = {
                    'F.Cu': BoardLayer.BL_F_Cu,
                    'B.Cu': BoardLayer.BL_B_Cu,
                }
                # Add internal layers to the map
                for i in range(1, 31):
                    layer_map[f'In{i}.Cu'] = getattr(BoardLayer, f'BL_In{i}_Cu', None)
                start_layer = layer_map.get(start_layer_str, BoardLayer.BL_F_Cu)
                end_layer = layer_map.get(end_layer_str, BoardLayer.BL_B_Cu)

            selected_only = config_dict.get('selected_only', False)

            stitch_mode = self._get_stitch_mode(config_dict)
            logger.debug(f"Stitch mode: {stitch_mode}")

            config = StitchingConfig(
                net_names=net_names,
                via_diameter_nm=from_mm(config_dict['via_size']),
                via_drill_nm=from_mm(config_dict['via_drill']),
                grid_spacing_nm=from_mm(config_dict['grid_spacing']),
                stagger_rows=config_dict['stagger_rows'],
                clearance_nm=from_mm(config_dict['clearance']),
                boundary_clearance_nm=from_mm(config_dict['boundary_clearance']),
                random_offset=config_dict.get('random_offset', False),
                random_offset_max_nm=from_mm(config_dict.get('random_offset_max', 0.2)),
                mode=stitch_mode,
                fence_spacing_nm=from_mm(config_dict.get('fence_spacing', 1.0)),
                fence_offset_nm=from_mm(config_dict.get('fence_offset', 0.5)),
                fence_both_sides=config_dict.get('fence_both_sides', True),
                selected_only=selected_only,
                via_type=via_type,
                start_layer=start_layer,
                end_layer=end_layer,
                board_corner_radius_nm=from_mm(config_dict.get('board_corner_radius', 0.0)),
            )
            logger.debug("Config created")

            def progress_callback(current, total, message):
                self.update_status(message=message)
                app = wx.GetApp()
                if app:
                    app.Yield()

            # Get selected zones or tracks as needed
            selected_zones = None
            selected_tracks = None
            if stitch_mode == StitchMode.FENCE_TRACE:
                selected_tracks = get_selected_tracks(self.board)
                logger.debug(f"Found {len(selected_tracks)} selected tracks")
            elif selected_only:
                selected_zones = get_selected_zones(self.board)
                logger.debug(f"Found {len(selected_zones) if selected_zones else 0} selected zones")

            logger.info("Starting generate_via_stitching...")
            self.result = generate_via_stitching(self.board, config, progress_callback, selected_zones, selected_tracks)
            logger.info(f"generate_via_stitching complete: {self.result.valid} valid vias")

            # Format rejection reasons
            if self.result.rejected_reasons:
                reasons = ", ".join([f"{k}: {v}" for k, v in self.result.rejected_reasons.items()])
                message = f"Preview complete. {self.result.valid} vias ready. Rejected: {reasons}"
            else:
                message = f"Preview complete. {self.result.valid} vias ready to place."

            self.update_status(
                zones=self.result.zones_found,
                candidates=self.result.candidates,
                valid=self.result.valid,
                rejected=self.result.rejected,
                message=message
            )
            logger.info("on_preview complete")

        except Exception as e:
            logger.exception(f"Error in on_preview: {e}")
            self.update_status(message=f"Error: {e}")
            wx.MessageBox(f"Error during preview: {e}", "Error", wx.OK | wx.ICON_ERROR)

    def on_apply(self, event):
        if not self.result or not self.result.vias:
            wx.MessageBox("No vias to place. Run Preview first.", "Error", wx.OK | wx.ICON_ERROR)
            return

        self.update_status(message=f"Placing {len(self.result.vias)} vias...")
        wx.GetApp().Yield()

        try:
            # Log intended net
            intended_net = self.result.vias[0].net if self.result.vias else None
            logger.info(f"Creating {len(self.result.vias)} vias with net: {intended_net.name if intended_net else 'None'}")

            # Create the vias - they already have the correct net set
            created = self.board.create_items(self.result.vias)
            logger.info(f"Created {len(created)} vias")

            # Note: Grouping is not yet supported in the kipy API (Group is marked as TODO).
            msg = f"Successfully created {len(created)} vias."
            wx.MessageBox(msg, "Via Stitcher", wx.OK | wx.ICON_INFORMATION)
            self.EndModal(wx.ID_OK)
        except Exception as e:
            logger.exception(f"Error creating vias: {e}")
            wx.MessageBox(f"Error creating vias: {e}", "Error", wx.OK | wx.ICON_ERROR)

    def on_delete_existing(self, event):
        """Delete existing stitching vias."""
        config_dict = self.get_config()
        net_names = [config_dict['net_name']]

        matching_vias = find_stitching_vias(
            self.board,
            net_names,
            from_mm(config_dict['via_size']),
            from_mm(config_dict['via_drill'])
        )

        if not matching_vias:
            wx.MessageBox("No matching stitching vias found.", "Info", wx.OK | wx.ICON_INFORMATION)
            return

        result = wx.MessageBox(
            f"Found {len(matching_vias)} stitching vias matching the current settings.\n\nDelete them?",
            "Delete Stitching Vias",
            wx.YES_NO | wx.ICON_QUESTION
        )

        if result == wx.YES:
            try:
                self.board.remove_items(matching_vias)
                wx.MessageBox(f"Deleted {len(matching_vias)} vias.", "Via Stitcher", wx.OK | wx.ICON_INFORMATION)
                # Refresh preview
                self.on_preview(None)
            except Exception as e:
                wx.MessageBox(f"Error deleting vias: {e}", "Error", wx.OK | wx.ICON_ERROR)


def main():
    """Main entry point for the Via Stitcher plugin."""
    import time
    start_time = time.time()

    logger.info("=" * 60)
    logger.info("Via Stitcher main() called")
    logger.info(f"Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Check if a wx.App already exists (when running inside KiCad)
        existing_app = wx.GetApp()
        if existing_app:
            logger.info(f"Using existing wx.App: {existing_app}")
            app = existing_app
        else:
            logger.info("Creating new wx.App")
            app = wx.App()

        logger.info(f"wx.App ready at {time.time() - start_time:.3f}s")

        logger.info("Creating ViaStitcherApp dialog...")
        dialog = ViaStitcherApp()
        logger.info(f"Dialog created at {time.time() - start_time:.3f}s")

        # ShowModal() handles showing the dialog - we just need to ensure it comes to front
        # Centre the dialog on screen
        dialog.CentreOnScreen()

        logger.info(f"Showing modal at {time.time() - start_time:.3f}s")
        # Flush logs before blocking on modal
        for handler in logger.handlers:
            handler.flush()

        result = dialog.ShowModal()
        logger.info(f"Dialog closed with result: {result} at {time.time() - start_time:.3f}s")

        dialog.Destroy()
        logger.info("Dialog destroyed")

    except Exception as e:
        logger.error(f"Error in main(): {e}")
        logger.error(traceback.format_exc())
        # Show error in a message box if possible
        try:
            wx.MessageBox(
                f"Via Stitcher Error:\n\n{e}\n\nSee ~/via_stitcher.log for details.",
                "Via Stitcher Error",
                wx.OK | wx.ICON_ERROR
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    logger.info("Running as __main__")
    main()
else:
    logger.info(f"Module imported as '{__name__}' (not __main__)")
