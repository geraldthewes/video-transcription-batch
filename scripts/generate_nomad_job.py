#!/usr/bin/env python3
"""
Generate Nomad HCL job specification for S3-based batch transcription.
"""

import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

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

    # Target nodes with GPU capability
    constraint {{
      attribute = "${{meta.gpu-capable}}"
      value     = "true"
    }}

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

      # Environment variables for v4.0.0 unified S3 structure
      env {{
{env_vars}
      }}

      # Vault template for AWS credentials
      template {{
        data = <<EOF
{{{{ with secret "{aws_secret_path}" }}}}
AWS_ACCESS_KEY_ID = "{{{{ .Data.data.access_key }}}}"
AWS_SECRET_ACCESS_KEY = "{{{{ .Data.data.secret_key }}}}"
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
        # Note: GPU allocation handled by constraint, not device block
        # since device detection may not be working properly
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

    # Load environment variables from .env file
    load_dotenv()

    # Use values from .env or args (args take precedence)
    transcriber_bucket = args.transcriber_bucket or os.getenv('S3_TRANSCRIBER_BUCKET')
    transcriber_prefix = args.transcriber_prefix or os.getenv('S3_TRANSCRIBER_PREFIX', '')
    ollama_url = args.ollama_url or os.getenv('OLLAMA_URL')
    aws_region = args.region or os.getenv('AWS_REGION', 'us-east-1')
    s3_endpoint = args.s3_endpoint or os.getenv('S3_ENDPOINT_URL')
    datacenter = args.datacenter or os.getenv('NOMAD_DATACENTER', 'dc1')

    if not transcriber_bucket:
        raise ValueError("S3_TRANSCRIBER_BUCKET must be set in .env file or provided via --transcriber-bucket")
    if not ollama_url:
        raise ValueError("OLLAMA_URL must be set in .env file or provided via --ollama-url")

    # Load resource configuration from S3 if requested
    cpu = args.cpu
    memory = args.memory
    gpu_count = args.gpu_count

    if args.load_resources_from_s3:
        try:
            manager = S3BatchManager(
                aws_region=aws_region,
                s3_endpoint=s3_endpoint,
                transcriber_bucket=transcriber_bucket,
                transcriber_prefix=transcriber_prefix,
            )
            resource_config = manager.download_resource_config(args.job_id)
            if resource_config:
                cpu = resource_config.get('cpu', cpu)
                memory = resource_config.get('memory', memory)
                gpu_count = resource_config.get('gpu_count', gpu_count)
                print(f"📊 Loaded resource config from S3: CPU={cpu}MHz, Memory={memory}MB, GPU={gpu_count}")
            else:
                print(f"⚠️  No resource config found in S3, using defaults")
        except Exception as e:
            print(f"⚠️  Failed to load resource config from S3: {e}")
            print(f"💻 Using command-line/default values")

    # Generate environment variables for v4.0.0 unified structure
    env_vars = {
        'S3_TRANSCRIBER_BUCKET': transcriber_bucket,
        'S3_TRANSCRIBER_PREFIX': transcriber_prefix,
        'S3_JOB_ID': args.job_id,
        'OLLAMA_URL': ollama_url,
        'AWS_REGION': aws_region,
    }

    # Add S3 endpoint if specified
    if s3_endpoint:
        env_vars['S3_ENDPOINT'] = s3_endpoint

    # Add any extra environment variables
    for extra in args.extra_env:
        if '=' in extra:
            key, value = extra.split('=', 1)
            env_vars[key] = value
    
    # Format environment variables for HCL template
    env_lines = []
    for key, value in env_vars.items():
        env_lines.append(f'        {key} = "{value}"')

    env_vars_str = '\n'.join(env_lines)

    # Generate the job specification
    job_spec = NOMAD_JOB_TEMPLATE.format(
        job_name=args.job_name,
        datacenter=datacenter,
        vault_policy=args.vault_policy,
        docker_image=args.docker_image,
        env_vars=env_vars_str,
        aws_secret_path=args.aws_secret_path,
        hf_secret_path=args.hf_secret_path,
        cpu=cpu,
        memory=memory,
        gpu_count=gpu_count
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
        description="Generate Nomad HCL job specification for v4.0.0 unified S3-based batch transcription",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example (reads most settings from .env file):
  generate-nomad-job \\
    --job-id 18517e9c-f624-4a16-bc10-a9236dbea7e1 \\
    --job-name video-transcription-batch

With custom settings:
  generate-nomad-job \\
    --job-id 18517e9c-f624-4a16-bc10-a9236dbea7e1 \\
    --job-name video-transcription-batch \\
    --transcriber-bucket custom-bucket \\
    --ollama-url http://custom-ollama:11434
        """
    )

    # Required arguments
    parser.add_argument('--job-id', required=True, help='S3 job ID for tasks/results')
    parser.add_argument('--job-name', required=True, help='Nomad job name')

    # Optional arguments (read from .env by default)
    parser.add_argument('--transcriber-bucket', help='S3 transcriber bucket (or use S3_TRANSCRIBER_BUCKET from .env)')
    parser.add_argument('--transcriber-prefix', help='S3 transcriber prefix (or use S3_TRANSCRIBER_PREFIX from .env)')
    parser.add_argument('--ollama-url', help='Ollama service URL (or use OLLAMA_URL from .env)')
    
    # Docker and infrastructure
    parser.add_argument('--docker-image', default='registry.cluster:5000/video-transcription-batch:v4.0.0',
                        help='Docker image for transcription service')
    parser.add_argument('--datacenter', help='Nomad datacenter (or use NOMAD_DATACENTER from .env, defaults to dc1)')

    # S3 configuration
    parser.add_argument('--region', help='AWS region (or use AWS_REGION from .env, defaults to us-east-1)')
    parser.add_argument('--s3-endpoint', help='Custom S3 endpoint URL (or use S3_ENDPOINT_URL from .env)')
    
    # Resource allocation (increased defaults for AI/ML workloads)
    parser.add_argument('--cpu', type=int, default=8000, help='CPU allocation in MHz (default: 8000)')
    parser.add_argument('--memory', type=int, default=16384, help='Memory allocation in MB (default: 16384)')
    parser.add_argument('--gpu-count', type=int, default=1, help='Number of GPUs to allocate (default: 1)')
    parser.add_argument('--load-resources-from-s3', action='store_true', help='Load resource config from S3 job (overrides --cpu/--memory/--gpu-count)')
    
    # Vault configuration
    parser.add_argument('--vault-policy', default='transcription-policy',
                        help='Vault policy for accessing secrets')
    parser.add_argument('--aws-secret-path', default='secret/aws/transcription',
                        help='Vault path for AWS credentials')
    parser.add_argument('--hf-secret-path', default='secret/hf/transcription',
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