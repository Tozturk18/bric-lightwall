# =============================================================================
# wall/config.py – LED wall layout configuration
#
# All dimensions are driven by constructor arguments so the code is
# completely agnostic about the physical installation.
#
# Example – 128×128 wall, 2×2 grid of 64×64 tiles, four Pis:
#
#   cfg = WallConfig(
#       rows   = 2,
#       cols   = 2,
#       tile_w = 64,
#       tile_h = 64,
#       hosts  = [
#           ("10.42.0.2", 8765),   # tile 0  (row 0, col 0)
#           ("10.42.0.3", 8765),   # tile 1  (row 0, col 1)
#           ("10.42.0.5", 8765),   # tile 2  (row 1, col 1) ← snake reverses row 1
#           ("10.42.0.4", 8765),   # tile 3  (row 1, col 0) ← snake reverses row 1
#       ],
#   )
#
# Snake-order tile numbering (matches tessellation.py):
#
#   row 0  →  [ 0 ][ 1 ][ 2 ]  (left → right)
#   row 1  →  [ 5 ][ 4 ][ 3 ]  (right → left)
#   row 2  →  [ 6 ][ 7 ][ 8 ]  (left → right)
#
# hosts must be supplied in that snake order.
# =============================================================================

from dataclasses import dataclass, field


@dataclass
class WallConfig:
    rows:   int               # number of tile rows
    cols:   int               # number of tile columns
    tile_w: int = 64          # tile width  in pixels (default: one panel wide)
    tile_h: int = 64          # tile height in pixels (default: two 32-px panels tall)
    port:   int = 8765        # default port (can be overridden per-host in hosts)
    hosts:  list = field(default_factory=list)
    # hosts: list of (ip_str, port_int) in snake order, one entry per tile.
    # If empty, WallSender will raise before connecting.

    # ---- derived properties -------------------------------------------------

    @property
    def wall_w(self) -> int:
        """Total wall width in pixels."""
        return self.cols * self.tile_w

    @property
    def wall_h(self) -> int:
        """Total wall height in pixels."""
        return self.rows * self.tile_h

    @property
    def num_tiles(self) -> int:
        return self.rows * self.cols

    # ---- helpers ------------------------------------------------------------

    @classmethod
    def from_args(
        cls,
        rows:   int,
        cols:   int,
        tile_w: int,
        tile_h: int,
        hosts:  list,          # list of "ip:port" strings
        default_port: int = 8765,
    ) -> "WallConfig":
        """
        Build a WallConfig from command-line style arguments.

        hosts is a list of strings in "ip" or "ip:port" format.
        Missing ports fall back to default_port.
        """
        parsed = []
        for h in hosts:
            if ":" in h:
                ip, port_str = h.rsplit(":", 1)
                parsed.append((ip, int(port_str)))
            else:
                parsed.append((h, default_port))

        cfg = cls(rows=rows, cols=cols, tile_w=tile_w, tile_h=tile_h,
                  port=default_port, hosts=parsed)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if len(self.hosts) != self.num_tiles:
            raise ValueError(
                f"WallConfig: expected {self.num_tiles} hosts "
                f"({self.rows}×{self.cols}), got {len(self.hosts)}"
            )