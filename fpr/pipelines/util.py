import io
import traceback


def exc_to_str() -> str:
    tb_file = io.StringIO()
    traceback.print_exc(file=tb_file)
    return tb_file.getvalue()
