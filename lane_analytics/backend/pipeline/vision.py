# Sobel/HLS thresholding and perspective transforms
import cv2
import numpy as np


class VisionProcessor:
    """
    Executes geometric homography modifications and spatial matrix thresholding
    to extract isolated lane markers from complex environments.
    """

    def __init__(self, frame_width: int, frame_height: int):
        self.width = frame_width
        self.height = frame_height

        w, h = float(frame_width), float(frame_height)

        # ROI expressed as fractions of the 1280×720 reference resolution so
        # the trapezoid scales correctly to any input resolution (e.g. 960×540).
        # Reference points (1280×720):
        #   Top-Left  [585, 460]  → (0.457, 0.639)
        #   Bot-Left  [203, 720]  → (0.159, 1.000) — clip to h-1 to stay in frame
        #   Bot-Right [1127, 720] → (0.881, 1.000)
        #   Top-Right [695, 460]  → (0.543, 0.639)
        self.src_coords = np.float32([
            [0.457 * w, 0.639 * h],   # Top-Left
            [0.159 * w, h - 1],        # Bottom-Left
            [0.881 * w, h - 1],        # Bottom-Right
            [0.543 * w, 0.639 * h],   # Top-Right
        ])

        self.dst_coords = np.float32([
            [0.25 * w, 0],
            [0.25 * w, h],
            [0.75 * w, h],
            [0.75 * w, 0],
        ])

        self.M = cv2.getPerspectiveTransform(self.src_coords, self.dst_coords)
        self.M_inverse = cv2.getPerspectiveTransform(self.dst_coords, self.src_coords)

    def generate_binary_mask(
        self,
        frame: np.ndarray,
        s_threshold=(170, 255),
        sobel_x_threshold=(20, 100)
    ) -> np.ndarray:
        """
        Fuses Sobel edge gradients with HLS space saturation filters to preserve
        structural data under high-exposure lighting shifts.
        """
        # Convert to HLS color space and isolate Saturation channel
        hls = cv2.cvtColor(frame, cv2.COLOR_BGR2HLS)
        s_channel = hls[:, :, 2]

        # Isolate Grayscale intensity and calculate directional Sobel operator
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        absolute_sobel = np.absolute(sobel_x)

        # Scale to 8-bit array matrices safely
        max_sobel = np.max(absolute_sobel)
        scaled_sobel = np.uint8(255 * absolute_sobel / max_sobel) if max_sobel > 0 else absolute_sobel

        # Construct bitwise Boolean masks
        binary_sobel = np.zeros_like(scaled_sobel)
        binary_sobel[(scaled_sobel >= sobel_x_threshold[0]) & (scaled_sobel <= sobel_x_threshold[1])] = 1

        binary_saturation = np.zeros_like(s_channel)
        binary_saturation[(s_channel >= s_threshold[0]) & (s_channel <= s_threshold[1])] = 1

        # Compute bitwise logical OR union vector
        fused_binary = np.zeros_like(binary_sobel)
        fused_binary[(binary_saturation == 1) | (binary_sobel == 1)] = 1
        return fused_binary

    def project_to_birds_eye(self, binary_frame: np.ndarray) -> np.ndarray:
        """Warp binary frame to top-down bird's-eye perspective."""
        return cv2.warpPerspective(binary_frame, self.M, (self.width, self.height), flags=cv2.INTER_LINEAR)

    def project_to_field_view(self, warped_frame: np.ndarray) -> np.ndarray:
        """Invert warp back to original camera perspective."""
        return cv2.warpPerspective(warped_frame, self.M_inverse, (self.width, self.height), flags=cv2.INTER_LINEAR)

    def encode_frame_jpeg(self, frame: np.ndarray, quality: int = 75) -> bytes:
        """
        Encode an OpenCV BGR frame to JPEG bytes for WebSocket streaming.
        Quality is kept at 75 to balance bandwidth vs. visual fidelity.
        """
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buffer.tobytes()
