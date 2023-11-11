import random
import time

from paper_rq.decorators import job


@job("paper:default")
def sleep(delay):
    time.sleep(delay)
    return delay


@job("paper:default")
def unstable_sleep(delay):
    time.sleep(delay)
    if random.randint(0, 3) == 2:
        raise RuntimeError("Bad luck...")
    return delay


@job("paper:default")
def print_info():
    print("Job started at {}".format(time.time()))
    time.sleep(1)
    print(
        ("Fusce commodo aliquam arcu. Pellentesque ut neque. Nam commodo suscipit quam. "
         "Morbi nec metus. Praesent metus tellus, elementum eu, semper a, adipiscing nec, purus.\n\n"
         "Vivamus consectetuer hendrerit lacus. Etiam vitae tortor. Vestibulum dapibus "
         "nunc ac augue. Sed hendrerit. Ut leo.\n"
         "Sed cursus turpis vitae tortor. Cras ultricies mi eu turpis hendrerit fringilla. "
         "Cras varius. Phasellus consectetuer vestibulum elit. Suspendisse potenti.\n"
         "Phasellus gravida semper nisi. In ac felis quis tortor malesuada pretium. "
         "Nulla facilisi. Vestibulum volutpat pretium libero. Praesent egestas neque eu enim.\n\n"
         "Etiam ut purus mattis mauris sodales aliquam. Aliquam lobortis. "
         "Aenean viverra rhoncus pede. Praesent vestibulum dapibus nibh. "
         "Aenean tellus metus, bibendum sed, posuere ac, mattis non, nunc."
         )
    )
    raise RuntimeError("Something wrong")
