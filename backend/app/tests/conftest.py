import os
import tempfile

# 必须在 import app.* 之前指定独立数据目录，避免污染开发库
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="changeflow_test_"))
