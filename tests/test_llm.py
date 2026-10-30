from langchain_core.messages import HumanMessage
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
    assert llm.max_tokens == settings.agent.max_tokens

def test_claude_model_without_a_key():

    with patch.object(settings.agent, 'model', 'claude-sonnet-5-5'), patch.dict(os.environ):
        os.environ.pop('ANTHROPIC_API_KEY', None)

        with pytest.raises(ValueError, match='ANTHROPIC_API_KEY is not set.'):
            model.get_llm()

@pytest.mark.parametrize('name', ['gpt-5', 'GPT-4o', 'o3-mini', 'chatgpt-4o-latest'])
def test_openai_model_with_a_key(name):

    with patch.object(settings.agent, 'model', name), patch.object(settings.agent, 'url', 'http://localhost:8000/v1'), patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
        assert settings.agent.provider == 'openai'
        llm = model.get_llm()

    assert type(llm).__name__ == 'ChatOpenAI'
    assert llm.model_name == name
    assert llm.openai_api_base != 'http://localhost:8000/v1'
    assert llm.openai_api_key.get_secret_value() == 'test-key'
    assert llm._get_request_payload([HumanMessage(content='hi')])['max_completion_tokens'] == settings.agent.max_tokens

def test_openai_model_without_a_key():

    with patch.object(settings.agent, 'model', 'gpt-5'), patch.dict(os.environ):
        os.environ.pop('OPENAI_API_KEY', None)

        with pytest.raises(ValueError, match='OPENAI_API_KEY is not set.'):
            model.get_llm()

@pytest.mark.parametrize('name, expected', [('claude-sonnet-5-5', ['AnthropicPromptCachingMiddleware']), ('gpt-5', []), ('gemma4', [])])
def test_prompt_caching_middleware(name, expected):

    with patch.object(settings.agent, 'model', name):
        assert [type(item).__name__ for item in model.middleware()] == expected

@pytest.mark.parametrize('name', ['gemma4', 'mlx-community/gemma-4-12b-it-8bit', 'llama3.1', 'ollama/opus'])
def test_other_names_are_local(name):

    with patch.object(settings.agent, 'model', name):
        assert settings.agent.provider == 'local'

def test_local_model_with_a_url():

    with patch.object(settings.agent, 'model', 'gemma4'), patch.object(settings.agent, 'url', 'http://localhost:8000/v1'):
        llm = model.get_llm()

    assert type(llm).__name__ == 'ChatOpenAI'
    assert llm.model_name == 'gemma4'
    assert llm.openai_api_base == 'http://localhost:8000/v1'
    assert llm._get_request_payload([HumanMessage(content='hi')])['max_completion_tokens'] == settings.agent.max_tokens

def test_local_model_without_a_url():

    with patch.object(settings.agent, 'model', 'gemma4'), patch.object(settings.agent, 'url', None):
        with pytest.raises(ValueError, match='Missing URL to call local model.'):
            model.get_llm()
