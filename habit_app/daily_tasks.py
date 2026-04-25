from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DailyTask:
    id: str
    title: str
    category: str
    description: str
    coin_reward: int
    difficulty: str = "medium"
    frequency: str = "daily"

    def to_dict(self):
        return asdict(self)


TASK_LIBRARY = [
    DailyTask(
        id="warmup-walk",
        title="10 Minute Walk",
        category="Warmup",
        description="Loosen up, get outside, and pick up momentum before the heavier work.",
        coin_reward=5,
        difficulty="easy",
    ),
    DailyTask(
        id="strength-circuit",
        title="Bodyweight Circuit",
        category="Strength",
        description="Finish 3 rounds of squats, push-ups, and lunges with steady pacing.",
        coin_reward=12,
        difficulty="medium",
    ),
    DailyTask(
        id="mobility-flow",
        title="Mobility Flow",
        category="Recovery",
        description="Spend 12 minutes opening hips, shoulders, and hamstrings.",
        coin_reward=8,
        difficulty="easy",
    ),
]


def all_daily_tasks():
    return [task.to_dict() for task in TASK_LIBRARY]


def find_daily_task(task_id):
    return next((task for task in TASK_LIBRARY if task.id == task_id), None)
