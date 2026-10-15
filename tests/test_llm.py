from pipelinespec.utils.llm import model
from pipelinespec import settings
from unittest.mock import patch
import pytest
import os

def test_claude_model_with_a_key():

    with patch.object(settings.agent, 'model', 'claude-sonnet-5-5'), patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
        llm = model.get_llm()

    assert type(llm).__name__ == 'ChatAnthropic'
    assert llm.model == 'claude-sonnet-5-5'

def test_claude_model_without_a_key():

    with patch.object(settings.agent, 'model', 'claude-sonnet-5-5'), patch.dict(os.environ):
        os.environ.pop('ANTHROPIC_API_KEY', None)

        with pytest.raises(ValueError, match='ANTHROPIC_API_KEY is not set.'):
            model.get_llm()

def test_local_model_with_a_url():

    with patch.object(settings.agent, 'model', 'gemma4'), patch.object(settings.agent, 'url', 'http://localhost:8000/v1'):
        llm = model.get_llm()

    assert type(llm).__name__ == 'ChatOpenAI'
    assert llm.model_name == 'gemma4'
    assert llm.openai_api_base == 'http://localhost:8000/v1'

def test_local_model_without_a_url():

    with patch.object(settings.agent, 'model', 'gemma4'), patch.object(settings.agent, 'url', None):
        with pytest.raises(ValueError, match='Missing URL to call local model.'):
            model.get_llm()
