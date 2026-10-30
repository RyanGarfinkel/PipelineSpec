from langchain_core.language_models import BaseChatModel
from singleton_decorator import singleton
from pipelinespec import settings
import os

@singleton
class Model:

    def get_llm(self) -> BaseChatModel:

        if settings.agent.provider == 'anthropic':
            return self.__anthropic()

        if settings.agent.provider == 'openai':
            return self.__openai()

        return self.__local()

    def middleware(self) -> list:

        if settings.agent.provider != 'anthropic':
            return []

        from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

        return [AnthropicPromptCachingMiddleware()]

    def __anthropic(self) -> BaseChatModel:

        if not os.environ.get('ANTHROPIC_API_KEY'):
            raise ValueError('ANTHROPIC_API_KEY is not set.')

        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=settings.agent.model, max_tokens=settings.agent.max_tokens)

    def __openai(self) -> BaseChatModel:

        if not os.environ.get('OPENAI_API_KEY'):
            raise ValueError('OPENAI_API_KEY is not set.')

        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=settings.agent.model, max_tokens=settings.agent.max_tokens)

    def __local(self) -> BaseChatModel:

        if settings.agent.url is None:
            raise ValueError('Missing URL to call local model.')

        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=settings.agent.model, base_url=settings.agent.url, api_key='not-needed', max_tokens=settings.agent.max_tokens)

model = Model()
