import logging
from common.llm_services import LLM_Model
from common.logs.log import req_id_cv
from common.logs.logwriter import LogWriter

logger = logging.getLogger(__name__)


class Ollama(LLM_Model):
    def __init__(self, config):
        super().__init__(config)
        from langchain_community.llms import Ollama as lc_Ollama

        model_name = config["llm_model"]
        self.llm = lc_Ollama(model=model_name, temperature=config["model_kwargs"]["temperature"], base_url=config.get("base_url", "http://localhost:11434"))
        self.prompt_path = config["prompt_path"]
        LogWriter.info(
            f"request_id={req_id_cv.get()} instantiated Ollama model_name={model_name}"
        )
