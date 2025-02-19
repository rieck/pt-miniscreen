import logging
import threading

from ..component import Component
from ..utils import transition

logger = logging.getLogger(__name__)


class Stack(Component):
    transition_duration = 0.25
    width = 0
    default_state = {
        "x_position": 0,
        "stack": [],
        "active_transition": None,
        "elements_to_pop": 0,
    }

    def cleanup(self):
        self._cleanup_transition.set()

    def __init__(self, initial_stack=[], **kwargs):
        super().__init__(**kwargs)

        self._cleanup_transition = threading.Event()

        # setup initial stack
        self.state["stack"] = [
            self.create_child(Component) for Component in initial_stack
        ]

    @property
    def active_component(self):
        try:
            # when popping the top component is being removed and so isn't active
            if self.state["active_transition"] == "POP":
                return self.state["stack"][-1 - self.state.get("elements_to_pop")]

            # active component is the top item
            return self.state["stack"][-1]

        # if index out of range return None
        except IndexError:
            return None

    @property
    def active_index(self):
        try:
            return self.state["stack"].index(self.active_component)

        # if active_component not in stack return None
        except ValueError:
            return None

    @property
    def stack(self):
        return self.state["stack"]

    def _push_transition(self):
        # only animate transition if we know our width
        if self.width:
            for step in transition(self.width, self.transition_duration):
                if self._cleanup_transition.is_set():
                    return

                self.state.update(
                    {"x_position": min(self.width, self.state["x_position"] - step)}
                )

        self.state.update({"active_transition": None})

    def _pop_transition(self, elements=1):
        # only animate transition if we know our width
        if self.width:
            for step in transition(self.width * elements, self.transition_duration):
                if self._cleanup_transition.is_set():
                    return

                self.state.update(
                    {
                        "x_position": min(
                            self.width * elements, self.state["x_position"] + step
                        )
                    }
                )

        stack = self.state["stack"]
        for _ in range(elements):
            self.remove_child(stack.pop())
        self.state.update(
            {"stack": stack, "active_transition": None, "elements_to_pop": 0}
        )

    @property
    def is_popping(self):
        return self.state.get("active_transition") == "POP"

    def push(self, Component, animate=True):
        if self.state["active_transition"] is not None:
            logger.debug(f"Currently transitioning, ignoring push of {Component}")
            return

        # create new stack
        stack = self.state["stack"] + [self.create_child(Component)]

        if not animate:
            logger.debug(f"Pushing component {Component} without transition")
            self.state.update({"stack": stack})
            return

        logger.debug(f"Starting a new push transition with component {Component}")
        self.state.update(
            {
                "active_transition": "PUSH",
                "x_position": self.width or 0,  # use 0 if self.width is None
                "stack": stack,
            }
        )

        threading.Thread(target=self._push_transition, daemon=True).start()

    def pop(self, animate=True, elements=1):
        if self.state["active_transition"] is not None:
            logger.debug("Currently transitioning, ignoring pop")
            return

        if len(self.state["stack"]) == 0:
            logger.debug("Unable to pop since stack is empty, ignoring pop")
            return

        if len(self.state["stack"]) < elements:
            logger.debug(
                f"Unable top pop {elements} elements, stack has {len(self.state['stack'])} elements"
            )
            return

        if not animate:
            logger.debug("Popping component without transition")
            stack = self.state["stack"].copy()
            for _ in range(elements):
                self.remove_child(stack.pop())
            self.state.update({"stack": stack})
            return

        logger.debug("Starting a new pop transition")
        self.state.update(
            {
                "active_transition": "POP",
                "elements_to_pop": elements,
                "x_position": 0,
            }
        )

        threading.Thread(
            target=self._pop_transition, args=(elements,), daemon=True
        ).start()

    def render(self, image):
        if len(self.state["stack"]) == 0:
            return image

        x_position = self.state["x_position"]
        foreground_component = self.state["stack"][-1]
        foreground_layer = foreground_component.render(image)

        # if no active transition only the top component needs to be rendered
        if not self.state["active_transition"]:
            return foreground_layer

        # crop foreground so it can be offset to the right by x_position
        right_bound = image.size[0] - x_position
        if right_bound < 0:
            # Newer versions of PIL have a crop method that will raise an error
            # if the crop boundaries are invalid.
            right_bound = 0
        crop_boundaries = (0, 0, right_bound, image.size[1])
        cropped_foreground_layer = foreground_layer.crop(crop_boundaries)

        # only foreground exists if one item on the stack
        if len(self.state["stack"]) == 1:
            image.paste(
                cropped_foreground_layer,
                (image.size[0] - cropped_foreground_layer.size[0], 0),
            )
            return image

        # render background layer and paste foreground offset to the right by x_position
        background_component = self.state["stack"][-2]
        background_layer = background_component.render(image)
        background_layer.paste(
            cropped_foreground_layer,
            (image.size[0] - cropped_foreground_layer.size[0], 0),
        )

        return background_layer
