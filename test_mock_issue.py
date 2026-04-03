import sys
from unittest.mock import MagicMock
mock_st = MagicMock()
sys.modules["streamlit"] = mock_st

import src.ui.app
print(mock_st.set_page_config.call_count)
