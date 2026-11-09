from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.bot.client import EmpleoRadarBot
from app.bot.views.job_views import APPLIED, create_job_card_layout
from app.jobs.models import JobMatchResult, JobPayload


@pytest.mark.parametrize("age", [5, 30, -1])
async def test_discord_rejects_old_or_future_publications_before_sending(age):
    bot = SimpleNamespace(
        is_ready=lambda: True, settings=SimpleNamespace(recovery_days=4),
        get_destination_channel_id=Mock(side_effect=AssertionError("No debe intentar enviar")),
    )
    job = JobPayload(
        title="Desarrollador", source_name="test", url="https://example.com/job",
        published_at=datetime.now(UTC) - timedelta(days=age),
    )
    result = await EmpleoRadarBot.notify_new_job(
        bot, job, JobMatchResult(score=70, summary="test"), 1
    )
    assert result is None
    bot.get_destination_channel_id.assert_not_called()


async def test_card_preserves_action_buttons_and_applied_state():
    job = JobPayload(title="Desarrollador Fullstack", source_name="test",
                     url="https://example.com/job", description="Descripción de la oferta")
    view = create_job_card_layout(job, job_id=42, decision=APPLIED)
    components = view.to_components()
    assert components[0]["type"] == 17  # Container Components V2, como la referencia.
    assert components[0]["accent_color"] == 0xF1C40F
    buttons = components[0]["components"][-1]["components"]
    assert [button["label"] for button in buttons] == [
        "Ver oferta", "Postulación marcada", "No me interesa",
    ]
    assert buttons[1]["disabled"] is True
