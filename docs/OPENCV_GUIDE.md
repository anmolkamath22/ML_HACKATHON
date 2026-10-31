# OpenCV guide

`cv/pipeline.py` loads through Pillow for format/EXIF safety, composites RGBA onto configured white (or black) background, converts to BGR, and downsizes only when the longest side exceeds `max_dimension`. It converts to grayscale, optionally runs non-local means denoising, optionally applies CLAHE with a conservative clip limit, detects Canny edges when enabled, and makes adaptive Gaussian or Otsu binary output. All stages are independent choices in `PreprocessingConfig`.

Outputs are original, normalized, grayscale, enhanced, edges, binary, and preprocessed PNG. Default recommendation is enhanced; callers can select normalized, edges or binary. Preserving alternatives lets later reconstruction experiments compare line/tonal representations without repeating input collection. The pipeline never overwrites the source input. Output width/height preserve aspect ratio. Pixel and dimension limits are configured in backend environment settings.
