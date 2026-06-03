# Sliding window poly-fitting and geometric math
import numpy as np
import cv2


class LaneTracker:
    """
    Fits continuous polynomial splines across isolated pixel coordinates and
    extracts physical curvature and relative coordinate offsets.
    """

    def __init__(self, frame_height: int, frame_width: int):
        self.height = frame_height
        self.width = frame_width

        # Approximation constants translating pixel dimensions to US Highway structural standards
        self.meters_per_pixel_y = 30.0 / 720.0
        self.meters_per_pixel_x = 3.7 / 700.0

        # Cache previous fits for targeted search on subsequent frames
        self._left_fit_cache: np.ndarray | None = None
        self._right_fit_cache: np.ndarray | None = None

    def fit_lanes(self, warped_binary: np.ndarray):
        """
        Public dispatcher: uses targeted search when a prior fit exists,
        falls back to full sliding-window scan otherwise.
        """
        if self._left_fit_cache is not None and self._right_fit_cache is not None:
            result = self._fit_from_prior(warped_binary)
            if result[0] is not None:
                return result
        return self.fit_initial_lanes(warped_binary)

    def fit_initial_lanes(self, warped_binary: np.ndarray):
        """
        Sliding Window processing methodology to localize disjointed target boundaries
        across historical data voids.
        """
        # Scan bottom half of matrix image for dense concentration peaks
        histogram = np.sum(warped_binary[self.height // 2:, :], axis=0)
        midpoint = histogram.shape[0] // 2

        left_base = np.argmax(histogram[:midpoint])
        right_base = np.argmax(histogram[midpoint:]) + midpoint

        num_windows = 9
        window_height = self.height // num_windows

        # Fetch indexing arrays for non-zero pixels inside frame
        nonzero = warped_binary.nonzero()
        nonzero_y = np.array(nonzero[0])
        nonzero_x = np.array(nonzero[1])

        current_left = left_base
        current_right = right_base

        margin = 100
        min_pixels = 50

        left_lane_indices = []
        right_lane_indices = []

        for window in range(num_windows):
            win_y_low = self.height - (window + 1) * window_height
            win_y_high = self.height - window * window_height

            win_xleft_low = current_left - margin
            win_xleft_high = current_left + margin
            win_xright_low = current_right - margin
            win_xright_high = current_right + margin

            # Filter non-zero pixels inside bounding boxes
            good_left_inds = (
                (nonzero_y >= win_y_low) & (nonzero_y < win_y_high) &
                (nonzero_x >= win_xleft_low) & (nonzero_x < win_xleft_high)
            ).nonzero()[0]
            good_right_inds = (
                (nonzero_y >= win_y_low) & (nonzero_y < win_y_high) &
                (nonzero_x >= win_xright_low) & (nonzero_x < win_xright_high)
            ).nonzero()[0]

            left_lane_indices.append(good_left_inds)
            right_lane_indices.append(good_right_inds)

            if len(good_left_inds) > min_pixels:
                current_left = int(np.mean(nonzero_x[good_left_inds]))
            if len(good_right_inds) > min_pixels:
                current_right = int(np.mean(nonzero_x[good_right_inds]))

        try:
            left_lane_indices = np.concatenate(left_lane_indices)
            right_lane_indices = np.concatenate(right_lane_indices)
        except ValueError:
            # Fallback error handling if windows found zero features
            return None, None, 0.0, 0.0

        left_x = nonzero_x[left_lane_indices]
        left_y = nonzero_y[left_lane_indices]
        right_x = nonzero_x[right_lane_indices]
        right_y = nonzero_y[right_lane_indices]

        if left_x.size == 0 or right_x.size == 0:
            return None, None, 0.0, 0.0

        # Fit second order polynomials: f(y) = Ay^2 + By + C
        left_fit = np.polyfit(left_y, left_x, 2)
        right_fit = np.polyfit(right_y, right_x, 2)

        # Cache fits for the next frame's targeted search
        self._left_fit_cache = left_fit
        self._right_fit_cache = right_fit

        curvature_radius = self._compute_curvature(left_y, left_x, right_y, right_x)
        vehicle_offset = self._compute_offset(left_fit, right_fit)

        return left_fit, right_fit, curvature_radius, vehicle_offset

    def _fit_from_prior(self, warped_binary: np.ndarray):
        """
        Targeted search within a margin band around previous polynomial fits,
        skipping the expensive full histogram scan.
        """
        margin = 80
        nonzero = warped_binary.nonzero()
        nonzero_y = np.array(nonzero[0])
        nonzero_x = np.array(nonzero[1])

        lf = self._left_fit_cache
        rf = self._right_fit_cache

        left_lane_inds = (
            (nonzero_x > (lf[0] * nonzero_y**2 + lf[1] * nonzero_y + lf[2] - margin)) &
            (nonzero_x < (lf[0] * nonzero_y**2 + lf[1] * nonzero_y + lf[2] + margin))
        )
        right_lane_inds = (
            (nonzero_x > (rf[0] * nonzero_y**2 + rf[1] * nonzero_y + rf[2] - margin)) &
            (nonzero_x < (rf[0] * nonzero_y**2 + rf[1] * nonzero_y + rf[2] + margin))
        )

        left_x = nonzero_x[left_lane_inds]
        left_y = nonzero_y[left_lane_inds]
        right_x = nonzero_x[right_lane_inds]
        right_y = nonzero_y[right_lane_inds]

        if left_x.size < 200 or right_x.size < 200:
            # Not enough pixels — invalidate cache and trigger full scan next cycle
            self._left_fit_cache = None
            self._right_fit_cache = None
            return None, None, 0.0, 0.0

        left_fit = np.polyfit(left_y, left_x, 2)
        right_fit = np.polyfit(right_y, right_x, 2)

        self._left_fit_cache = left_fit
        self._right_fit_cache = right_fit

        curvature_radius = self._compute_curvature(left_y, left_x, right_y, right_x)
        vehicle_offset = self._compute_offset(left_fit, right_fit)

        return left_fit, right_fit, curvature_radius, vehicle_offset

    def _compute_curvature(self, left_y, left_x, right_y, right_x) -> float:
        """Re-fit polynomials inside scaled physical meter space."""
        left_fit_cr = np.polyfit(left_y * self.meters_per_pixel_y, left_x * self.meters_per_pixel_x, 2)
        right_fit_cr = np.polyfit(right_y * self.meters_per_pixel_y, right_x * self.meters_per_pixel_x, 2)

        eval_point = (self.height - 1) * self.meters_per_pixel_y

        # Compute tracking radius: R = (1 + (2Ay + B)^2)^(3/2) / |2A|
        left_curverad = (
            (1 + (2 * left_fit_cr[0] * eval_point + left_fit_cr[1]) ** 2) ** 1.5
        ) / np.absolute(2 * left_fit_cr[0])
        right_curverad = (
            (1 + (2 * right_fit_cr[0] * eval_point + right_fit_cr[1]) ** 2) ** 1.5
        ) / np.absolute(2 * right_fit_cr[0])

        return float(np.mean([left_curverad, right_curverad]))

    def _compute_offset(self, left_fit: np.ndarray, right_fit: np.ndarray) -> float:
        """Calculate vehicle displacement relative to track baseline center."""
        car_position = self.width / 2.0
        y_eval = self.height - 1

        left_x_bottom = left_fit[0] * (y_eval ** 2) + left_fit[1] * y_eval + left_fit[2]
        right_x_bottom = right_fit[0] * (y_eval ** 2) + right_fit[1] * y_eval + right_fit[2]

        lane_center = (left_x_bottom + right_x_bottom) / 2.0
        pixel_offset = car_position - lane_center
        return float(pixel_offset * self.meters_per_pixel_x)

    def build_overlay_frame(
        self,
        raw_frame: np.ndarray,
        warped_binary: np.ndarray,
        left_fit: np.ndarray,
        right_fit: np.ndarray,
        processor,  # VisionProcessor instance
    ) -> np.ndarray:
        """
        Renders the filled lane polygon and HUD text onto the original camera frame.
        Returns the composited BGR image ready for encoding.
        """
        h, w = raw_frame.shape[:2]
        plot_y = np.linspace(0, h - 1, h)
        left_fit_x = left_fit[0] * plot_y**2 + left_fit[1] * plot_y + left_fit[2]
        right_fit_x = right_fit[0] * plot_y**2 + right_fit[1] * plot_y + right_fit[2]

        warp_zero = np.zeros_like(warped_binary).astype(np.uint8)
        color_warp = np.dstack((warp_zero, warp_zero, warp_zero))

        pts_left = np.array([np.transpose(np.vstack([left_fit_x, plot_y]))])
        pts_right = np.array([np.flipud(np.transpose(np.vstack([right_fit_x, plot_y])))])
        pts = np.hstack((pts_left, pts_right))

        cv2.fillPoly(color_warp, np.int32([pts]), (0, 255, 0))

        new_warp = processor.project_to_field_view(color_warp)
        return cv2.addWeighted(raw_frame, 1.0, new_warp, 0.3, 0)
