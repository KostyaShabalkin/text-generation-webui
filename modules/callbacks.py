from queue import Queue
from threading import Thread

import torch
import transformers

import modules.shared as shared


# Copied from https://github.com/PygmalionAI/gradio-ui/
class _SentinelTokenStoppingCriteria(transformers.StoppingCriteria):

    def __init__(self, sentinel_token_ids: torch.LongTensor,
                 starting_idx: int):
        transformers.StoppingCriteria.__init__(self)
        self.sentinel_token_ids = sentinel_token_ids
        self.starting_idx = starting_idx

    def __call__(self, input_ids: torch.LongTensor,
                 _scores: torch.FloatTensor) -> bool:
        for sample in input_ids:
            trimmed_sample = sample[self.starting_idx:]
            # Can't unfold, output is still too tiny. Skip.
            if trimmed_sample.shape[-1] < self.sentinel_token_ids.shape[-1]:
                continue

            for window in trimmed_sample.unfold(
                    0, self.sentinel_token_ids.shape[-1], 1):
                if torch.all(torch.eq(self.sentinel_token_ids, window)):
                    return True
        return False

class Stream(transformers.StoppingCriteria):
    def __init__(self, callback_func=None):
        self.callback_func = callback_func

    def __call__(self, input_ids, scores) -> bool:
        if self.callback_func is not None:
            self.callback_func(input_ids[0])
        return False

class Iteratorize:

    """
    Transforms a function that takes a callback
    into a lazy iterator (generator).
    """

    def __init__(self, func, kwargs={}, callback=None):
        self.mfunc=func
        self.c_callback=callback
        self.q = Queue(maxsize=1)
        self.sentinel = object()
        self.kwargs = kwargs

        def _callback(val):
            self.q.put(val)

        def gentask():
            ret = self.mfunc(callback=_callback, **self.kwargs)
            self.q.put(self.sentinel)
            if self.c_callback:
                self.c_callback(ret)

        Thread(target=gentask).start()

    def __iter__(self):
        return self

    def __next__(self):
        obj = self.q.get(True,None)
        if obj is self.sentinel:
            raise StopIteration
        else:
            return obj
