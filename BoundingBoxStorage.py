
class BoundingBoxStorage:
    BBOXES = {
        "munich": (
            48.061,   # south
            11.360,   # west
            48.248,   # north
            11.722    # east
        ),

        "half_of_munich": (
            (48.061 + 48.118) / 2,
            (11.360 + 11.555) / 2,
            (48.248 + 48.145) / 2,
            (11.722 + 11.590) / 2
        ),

        "one_third_of_munich": (
            (48.061 + 48.118 * 2) / 3,
            (11.360 + 11.555 * 2) / 3,
            (48.248 + 48.145 * 2) / 3,
            (11.722 + 11.590 * 2) / 3
        ),

        "isarvorstadt": (
            48.118,
            11.555,
            48.145,
            11.590
        ),

        "regensburg": (
            48.980,
            12.040,
            49.070,
            12.160
        ),

        "nuernberg": (
            49.380,
            11.000,
            49.520,
            11.160
        ),
        "olching": (
            48.140,
            11.250,
            48.280,
            11.410
        ),
        "potsdam": (
            52.343,
            12.888,
            52.515,
            13.166
        ),
        "wedding": (
            52.5356771,
            13.3015376,
            52.5644452,
            13.3749244
        ),
        "berlin": (
            # Covers every Berlin district boundary, with a small margin.
            52.330,
            13.080,
            52.690,
            13.770
        ),
    }

    @classmethod
    def get(cls, name: str):
        result = cls.BBOXES.get(name.lower())
        if result is None:
            raise ValueError(f"No Bounding Box defined for '{name.lower()}'. Available options: {list(cls.BBOXES.keys())}")

        return result
