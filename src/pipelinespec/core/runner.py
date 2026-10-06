from pipelinespec.models import Job, TraceConfig, TraceResult, JobRun
from pipelinespec.tools import act, docker_compose
from singleton_decorator import singleton
import logging as log
import json

@singleton
class JobRunner:

    def execute(self, job: Job, config: TraceConfig) -> int:

        run_data = JobRun()

        # Sandbox/Trace setup
        with open(run_data.secrets_file, 'w') as f:
            for key, value in config.secrets.items():
                f.write(f'{key}={value}\n')

        with open(run_data.env_file, 'w') as f:
            for key, value in config.env.items():
                f.write(f'{key}={value}\n')

        with open(run_data.output_dir / 'network_policy.json', 'w') as f:
            json.dump([mock.model_dump() for mock in config.networks], f)

        # Call ACT
        try:
            docker_compose.up(run_data)
            return act.run(job, run_data, docker_compose.network(run_data))
        finally:
            docker_compose.save_logs(run_data)
            docker_compose.down(run_data)
        
        # Extract results

        # Return results

job_runner = JobRunner()
