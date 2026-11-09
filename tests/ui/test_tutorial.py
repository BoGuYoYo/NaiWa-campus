"""教程状态机测试（D7 五步：触发 → 显示 → 完成条件 → 持久化）。"""

from __future__ import annotations

from game.ui.tutorial import TutorialController


def make_controller(state, fixture_text_db):
    return TutorialController(state, fixture_text_db)


def test_move_step_completes_after_3_meters(fake_state, fixture_text_db):
    controller = make_controller(fake_state, fixture_text_db)
    assert controller.notify("enter_campus") == "tut.move"
    assert controller.notify("player_moved", distance_m=1.5) == "tut.move"
    assert controller.notify("player_moved", distance_m=1.4) == "tut.move"
    assert controller.notify("player_moved", distance_m=0.2) is None
    assert "tut.move" in fake_state.tutorial_done


def test_interact_completes_with_first_activity(fake_state, fixture_text_db):
    controller = make_controller(fake_state, fixture_text_db)
    controller.notify("enter_campus")
    controller.notify("player_moved", distance_m=10.0)
    assert controller.notify("near_interactable") == "tut.interact"
    assert controller.notify("activity_done") is None
    assert {"tut.move", "tut.interact"} <= fake_state.tutorial_done


def test_slots_step_closes_on_space(fake_state, fixture_text_db):
    controller = make_controller(fake_state, fixture_text_db)
    controller.notify("result_closed")
    assert controller.notify("key_space") is None
    assert "tut.slots" in fake_state.tutorial_done


def test_energy_step_triggered_below_40(fake_state, fixture_text_db):
    controller = make_controller(fake_state, fixture_text_db)
    assert controller.notify("low_energy") == "tut.energy"
    assert controller.banner_text() == "累了就去食堂或宿舍"
    controller.notify("key_space")
    assert "tut.energy" in fake_state.tutorial_done


def test_tab_step_opens_or_times_out(fake_state, fixture_text_db):
    controller = make_controller(fake_state, fixture_text_db)
    fake_state.day_index = 1  # 第 2 天（第 1 天日结算后）
    controller.notify("day_ended")
    assert controller.notify("tab_opened") is None
    assert "tut.tab" in fake_state.tutorial_done

    fake_state.tutorial_done = set()
    controller2 = make_controller(fake_state, fixture_text_db)
    controller2.notify("day_ended")
    for _ in range(40):
        controller2.notify("tick", dt=1.0)
    assert "tut.tab" in fake_state.tutorial_done


def test_done_steps_do_not_repeat_after_reload(fake_state, fixture_text_db):
    fake_state.tutorial_done = {"tut.move", "tut.interact"}
    controller = make_controller(fake_state, fixture_text_db)
    controller.notify("enter_campus")        # 已完成，不再显示
    assert controller.notify("near_interactable") is None
    assert controller.active_step is None


def test_only_one_step_at_a_time(fake_state, fixture_text_db):
    controller = make_controller(fake_state, fixture_text_db)
    assert controller.notify("enter_campus") == "tut.move"
    # tut.move 未完成时其他步骤不并行启动
    assert controller.notify("low_energy") == "tut.move"


def test_is_finished(fake_state, fixture_text_db):
    controller = make_controller(fake_state, fixture_text_db)
    fake_state.tutorial_done = {"tut.move", "tut.interact", "tut.slots", "tut.energy", "tut.tab"}
    assert controller.is_finished()
