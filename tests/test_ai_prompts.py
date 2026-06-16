from app.ai.prompts import select_prompt


def test_manager_uses_manager_prompt():
    config = {"system_prompt": "cliente", "manager_prompt": "admin"}
    assert select_prompt(config, "manager") == "admin"


def test_manager_falls_back_to_system_when_no_manager_prompt():
    config = {"system_prompt": "cliente", "manager_prompt": ""}
    assert select_prompt(config, "manager") == "cliente"


def test_client_uses_system_prompt():
    config = {"system_prompt": "cliente", "manager_prompt": "admin"}
    assert select_prompt(config, "client") == "cliente"
