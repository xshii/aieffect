"""资源管理器测试"""

from framework.core.resource import ResourceManager


class TestResourceManager:
    def test_self_mode_basic(self) -> None:
        rm = ResourceManager(mode="self", capacity=2)
        s = rm.status()
        assert s.capacity == 2
        assert s.in_use == 0
        assert s.available == 2

    def test_acquire_release(self) -> None:
        rm = ResourceManager(mode="self", capacity=2)

        assert rm.acquire("task1") is True
        assert rm.acquire("task2") is True
        assert rm.acquire("task3") is False  # 超出容量

        s = rm.status()
        assert s.in_use == 2
        assert s.available == 0
        assert "task1" in s.tasks

        rm.release("task1")
        s = rm.status()
        assert s.in_use == 1
        assert s.available == 1

    def test_capacity_minimum(self) -> None:
        rm = ResourceManager(mode="self", capacity=0)
        assert rm.capacity == 1  # 最小值为 1

    def test_release_extra(self) -> None:
        rm = ResourceManager(mode="self", capacity=2)
        rm.release("nonexistent")  # 不应报错
        assert rm.status().in_use == 0
