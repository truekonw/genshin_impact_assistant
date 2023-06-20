class GIABaseException(Exception):
    possible_reasons = []
    def __init__(self, *args: object, reason:str = None) -> None:
        super().__init__(*args)
        self.stop_task_flag = False # 当发生该异常时，是否结束所有Task。
        self.reason = reason
    
class TaskException(GIABaseException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)
        self.stop_task_flag = True


