from pipelinespec.models import Job, TraceConfig, TraceResult, JobRun
from singleton_decorator import singleton
from pipelinespec.tools import act
import logging as log

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

        # Call ACT
        return act.run(job, run_data)
        # Extract results

        # Return results

job_runner = JobRunner()
