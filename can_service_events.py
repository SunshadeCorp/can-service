from events import Events


class CanServiceEvents(Events):
    __events__ = ('on_start', 'on_stop', 'on_received', 'on_sent',)
