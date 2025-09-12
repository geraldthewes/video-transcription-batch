#!/usr/bin/env python3
"""
Generate Nomad HCL job specification for S3-based batch transcription.
"""

import argparse
import os
import sys
from pathlib import Path

# Add the parent directory to Python path to import transcription_client
sys.path.insert(0, str(Path(__file__).parent.parent))

from transcription_client.s3_batch import S3BatchManager


NOMAD_JOB_TEMPLATE = '''job "{job_name}" {{
  datacenters = ["{datacenter}"]
  type        = "batch"

  vault {{
    policies = ["{vault_policy}"]
  }}

  group "transcriber" {{
    count = 1

    restart {{
      attempts = 2
      delay    = "30s"
      interval = "5m"
      mode     = "fail"
    }}

    task "main" {{
      driver = "docker"

      config {{
        image = "{docker_image}"
        
        # Optional: configure logging
        logging {{
          type = "json-file"
          config {{
            max-file = "3"
            max-size = "10m"
          }}
        }}
      }}

      # Environment variables from S3BatchManager
      env {{
{env_vars}
      }}

      # Vault template for AWS credentials
      template {{
        data = <<EOF
{{{{ with secret "{aws_secret_path}" }}}}
AWS_ACCESS_KEY_ID = "{{{{ .Data.data.access_key_id }}}}"
AWS_SECRET_ACCESS_KEY = "{{{{ .Data.data.secret_access_key }}}}"
{{{{ end }}}}
EOF
        destination = "secrets/aws.env"
        env         = true
      }}

      # Optional: Vault template for HuggingFace token
      template {{
        data = <<EOF
{{{{ with secret "{hf_secret_path}" }}}}
HF_TOKEN = "{{{{ .Data.data.token }}}}"
{{{{ end }}}}
EOF
        destination = "secrets/hf.env"
        env         = true
      }}

      resources {{
        cpu    = {cpu}
        memory = {memory}
        
        device "nvidia/gpu" {{
          count = {gpu_count}
        }}
      }}

      # Logs for debugging
      logs {{
        max_files     = 5
        max_file_size = 10
      }}
    }}
  }}
}}'''


def generate_nomad_job(args):
    """Generate a Nomad job HCL file."""
    
    # Create S3BatchManager to generate environment variables
    manager = S3BatchManager(
        aws_region=args.region,
        s3_endpoint=args.s3_endpoint,
        tasks_bucket=args.tasks_bucket,
        results_bucket=args.results_bucket
    )
    
    # Generate environment variables
    env_vars = manager.create_nomad_env_vars(
        job_id=args.job_id,
        video_bucket=args.video_bucket,
        output_bucket=args.output_bucket,
        ollama_url=args.ollama_url,
        **dict(kv.split('=', 1) for kv in args.extra_env)
    )
    
    # Format environment variables for HCL template
    env_lines = []
    for key, value in env_vars.items():
        env_lines.append(f'        {key} = "{value}"')
    
    env_vars_str = '\\n'.join(env_lines)
    
    # Generate the job specification
    job_spec = NOMAD_JOB_TEMPLATE.format(
        job_name=args.job_name,
        datacenter=args.datacenter,
        vault_policy=args.vault_policy,
        docker_image=args.docker_image,
        env_vars=env_vars_str,
        aws_secret_path=args.aws_secret_path,
        hf_secret_path=args.hf_secret_path,
        cpu=args.cpu,
        memory=args.memory,
        gpu_count=args.gpu_count
    )
    
    # Write to file
    output_file = args.output or f"{args.job_name}.nomad"
    
    with open(output_file, 'w') as f:
        f.write(job_spec)
    
    print(f"✅ Generated Nomad job specification: {output_file}")
    print(f"🚀 Deploy with: nomad job run {output_file}")
    
    if args.dry_run:
        print("\\n📝 Job specification:")
        print(job_spec)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Nomad HCL job specification for S3-based batch transcription",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  generate-nomad-job \\
    --job-id abc-123-def \\
    --job-name video-transcription-abc123 \\
    --video-bucket my-videos \\
    --output-bucket my-transcripts \\
    --ollama-url http://ollama.service.consul:11434 \\
    --docker-image registry.cluster:5000/video-transcription-batch:latest
        """
    )
    
    # Required arguments
    parser.add_argument('--job-id', required=True, help='S3 job ID for tasks/results')
    parser.add_argument('--job-name', required=True, help='Nomad job name')
    parser.add_argument('--video-bucket', required=True, help='S3 bucket for storing videos')
    parser.add_argument('--output-bucket', required=True, help='S3 bucket for storing transcripts')
    parser.add_argument('--ollama-url', required=True, help='Ollama service URL')
    
    # Docker and infrastructure
    parser.add_argument('--docker-image', default='registry.cluster:5000/video-transcription-batch:latest',
                        help='Docker image for transcription service')
    parser.add_argument('--datacenter', default='dc1', help='Nomad datacenter')
    
    # S3 configuration
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--s3-endpoint', help='Custom S3 endpoint URL')
    parser.add_argument('--tasks-bucket', help='S3 bucket for tasks (or set S3_TASKS_BUCKET env var)')
    parser.add_argument('--results-bucket', help='S3 bucket for results (defaults to tasks bucket)')
    
    # Resource allocation
    parser.add_argument('--cpu', type=int, default=2000, help='CPU allocation in MHz')
    parser.add_argument('--memory', type=int, default=4096, help='Memory allocation in MB')
    parser.add_argument('--gpu-count', type=int, default=1, help='Number of GPUs to allocate')
    
    # Vault configuration
    parser.add_argument('--vault-policy', default='transcription-policy', 
                        help='Vault policy for accessing secrets')
    parser.add_argument('--aws-secret-path', default='secret/nomad/jobs/aws-credentials',
                        help='Vault path for AWS credentials')
    parser.add_argument('--hf-secret-path', default='secret/nomad/jobs/hf-token',
                        help='Vault path for HuggingFace token')
    
    # Additional options
    parser.add_argument('--extra-env', action='append', default=[],
                        help='Additional environment variables (format: KEY=value)')
    parser.add_argument('--output', help='Output file path (default: {job_name}.nomad)')
    parser.add_argument('--dry-run', action='store_true', help='Print job spec without saving')
    
    args = parser.parse_args()
    
    try:
        generate_nomad_job(args)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()