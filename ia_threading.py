import gc
import threading
from functools import wraps

from modules import devices, shared
from modules.sd_models import load_model, reload_model_weights

backup_sd_model = None
backup_ckpt_info = None
model_access_sem = threading.Semaphore(1)


def clear_cache():
    gc.collect()
    devices.torch_gc()


def webui_reload_model_weights(sd_model=None, info=None):
    try:
        reload_model_weights(sd_model=sd_model, info=info)
        # A1111 web UI PR #12396
        shared.opts.data["sd_model_checkpoint"] = info.title
        shared.opts.data["sd_checkpoint_hash"] = info.sha256
    except Exception:
        load_model(checkpoint_info=info)


def pre_unload_model_weights(sem):
    global backup_sd_model, backup_ckpt_info
    with sem:
        if shared.sd_model is not None:
            backup_sd_model = shared.sd_model
            backup_sd_model.to(devices.cpu)
            clear_cache()


def await_pre_unload_model_weights():
    global model_access_sem
    thread = threading.Thread(target=pre_unload_model_weights, args=(model_access_sem,))
    thread.start()
    thread.join()


def pre_reload_model_weights(sem):
    global backup_sd_model, backup_ckpt_info
    with sem:
        if backup_sd_model is not None:
            backup_sd_model.to(devices.device)
            backup_sd_model = None
        if shared.sd_model is not None and backup_ckpt_info is not None:
            webui_reload_model_weights(sd_model=shared.sd_model, info=backup_ckpt_info)
            backup_ckpt_info = None


def await_pre_reload_model_weights():
    global model_access_sem
    thread = threading.Thread(target=pre_reload_model_weights, args=(model_access_sem,))
    thread.start()
    thread.join()


def backup_reload_ckpt_info(sem, info):
    global backup_sd_model, backup_ckpt_info
    with sem:
        if backup_sd_model is not None:
            backup_sd_model.to(devices.device)
            backup_sd_model = None
        if shared.sd_model is not None:
            backup_ckpt_info = shared.sd_model.sd_checkpoint_info
            webui_reload_model_weights(sd_model=shared.sd_model, info=info)


def await_backup_reload_ckpt_info(info):
    global model_access_sem
    thread = threading.Thread(target=backup_reload_ckpt_info, args=(model_access_sem, info))
    thread.start()
    thread.join()


def post_reload_model_weights(sem):
    global backup_sd_model, backup_ckpt_info
    with sem:
        if backup_sd_model is not None:
            backup_sd_model.to(devices.device)
            backup_sd_model = None
        if shared.sd_model is not None and backup_ckpt_info is not None:
            webui_reload_model_weights(sd_model=shared.sd_model, info=backup_ckpt_info)
            backup_ckpt_info = None


def async_post_reload_model_weights():
    global model_access_sem
    thread = threading.Thread(target=post_reload_model_weights, args=(model_access_sem,))
    thread.start()


def acquire_release_semaphore(sem):
    with sem:
        pass


def await_acquire_release_semaphore():
    global model_access_sem
    thread = threading.Thread(target=acquire_release_semaphore, args=(model_access_sem,))
    thread.start()
    thread.join()


def clear_cache_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        clear_cache()
        res = func(*args, **kwargs)
        clear_cache()
        return res

    return wrapper


def post_reload_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        await_acquire_release_semaphore()
        res = func(*args, **kwargs)
        async_post_reload_model_weights()
        return res

    return wrapper
