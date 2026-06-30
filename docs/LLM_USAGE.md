# LLM Usage

ArchAPI supports real-time LLM-assisted API generation.

## Provider

Current provider: OpenAI Responses API

Default model: gpt-5-mini

## Environment variables

Set your OpenAI API key:

    export OPENAI_API_KEY="your-real-key"

Optionally set the model:

    export ARCHAPI_LLM_MODEL="gpt-5-mini"

## Python usage

    from archapi import ArchAPI

    engine = ArchAPI(
        "./my_backend_project",
        use_llm=True,
        llm_model="gpt-5-mini",
    )

    result = engine.generate_api(
        "Create authenticated POST API for user refund request",
        dry_run=True,
    )

    print(result.plan)
    print(result.validation_report)
    print(result.diff)

## Smoke test

    export OPENAI_API_KEY="your-real-key"
    ./scripts/test_openai_llm.sh

## Safety

Even with LLM generation enabled, ArchAPI still runs:

- architecture confidence checks
- generated-code validation
- policy checks
- dry-run generation by default
- overwrite protection
