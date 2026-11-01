# Discussion Questions

Answer the **Shared Questions** section plus the **one track section** specified in your email (Solutions Architect OR Data Engineer). 

Aim for 2-4 sentences per answer unless otherwise noted. We value clarity and depth over length.

---

## Shared Questions (everyone answers)

### 1. Troubleshooting

If you could not complete the assessment or got stuck at any point, what went wrong and what did you try to troubleshoot?

**Your answer:**

- I completed the assessment. All four sample documents ran through the pipeline and produced results.
- My home DNS blocked amazonaws.com, so the AWS CLI and Docker could not reach AWS. I checked it against Google’s DNS and switched my machine to public DNS.
- The Lambda functions use a container image, and AWS will not create them before the image exists. So I created the ECR repository first, pushed the image, and then applied the rest of the Terraform.
- make update-lambdas said it updated the functions, but it did nothing. It looked for Terraform outputs that did not exist, and the error was hidden. I added the missing outputs and checked that all four functions updated.
- A terraform plan that I stopped early left a lock on the state file. I checked that no Terraform command was still running and then removed the lock using its ID.
- The Extract step never received the document type, because the state machine only sent it the preprocess result. I changed the state machine to merge the preprocess and classify results with States.JsonMerge.
- My IAM user did not have permission to call Bedrock, so I could not test the prompts from my machine. I tested them through the deployed Lambdas instead.
- The first real run failed because Bedrock rejected the temperature setting for this model. My unit tests used a mocked Bedrock client, so they could not catch this. I removed the setting.
- My log messages did not show up in CloudWatch. The LOG_LEVEL setting was passed to the Lambdas but never used, so I set it in each handler.

### 2. Proof of Completion

Paste the S3 URI to one of your result files (e.g., `s3://nmd-genai-<your-name>-documents/results/<document-id>.json`).

**Your answer:**

s3://nmd-genai-meher-bajjuri-documents/results/drug-approval.json (all four samples have results under results/).


### 3. Prompt Engineering

How would you improve the classification prompt to handle ambiguous documents that could match multiple types? What techniques would you use to ensure consistent JSON output from the LLM?

**Your answer:**

My prompt describes each document type by its purpose with an example, tells the model to judge by the main purpose of the document, and gives it an "unknown" option so it does not have to guess. To handle documents that fit more than one type, I would add a few short examples of borderline cases, let the model return a main type plus other possible types, and send results with low confidence to a person for review. For consistent JSON, I give the model the exact format to reply in with a fixed list of allowed values, and my code checks every value and falls back to "unknown" if anything is wrong. This model does not accept a temperature setting, so in production I would also use Bedrock tool use with a JSON schema, which makes the API enforce the format.


### 4. Error Handling

How would you handle Bedrock throttling (429 errors) in a production pipeline? What retry strategy would you implement, and how would it interact with Step Functions' built-in error handling?

**Your answer:**

I let the Bedrock throttling error pass up from the Lambda instead of catching it, so Step Functions can retry the step. The Retry I added on Classify and Extract waits 5, 10, 20 and then 40 seconds between attempts, with random jitter so that many runs do not all retry at the same moment, and errors caused by bugs are not retried at all. The boto3 client also retries a few times inside the Lambda, so I would keep that number small to avoid stacking retries and running past the Lambda timeout. In production I would add a Catch that sends a document to a dead-letter queue after the last retry, and limit how many documents run at once so the pipeline stays under the Bedrock quota.


### 5. Enterprise Readiness

Assume a CTO prototyped this pipeline over a weekend using AI code assistants. It works for demos but needs to go to production for a Fortune 500 client.

Write a prioritized list of changes organized by:
1. **Must-fix before production** — what would block a launch?
    1. Limit the Lambda permissions. Right now they can call any Bedrock model and read and write the whole bucket.
    2. Encrypt the bucket with a KMS key and allow only HTTPS access, since the documents may be sensitive.
    3. Add a failure path. A failed run just stops today, so add a Catch, a dead-letter queue and alerts so no document is lost.
    4. Check the model output against a schema before saving it, and send low-confidence results for review.
    5. Deploy from a CI/CD pipeline with short-lived credentials instead of from a laptop with access keys, and tag each image with its git commit instead of latest.

2. **Should-fix in the first sprint** — what's important but not blocking?
    1. Set up CI to run lint, tests and terraform plan on every pull request.
    2. Add structured logs and CloudWatch alarms for failures, slow runs, throttling and token use.
    3. Build a small set of labeled test documents to measure accuracy whenever the prompt or model changes.
    4. Add a test after each deploy that uploads a sample and checks the result.
    5. Turn on image scanning in ECR and lifecycle rules for old files in S3.

3. **Nice-to-have for long-term maintainability** — what would you plan for later?
    1. Record the prompt version and schema version in every result.
    2. Add caching for repeated documents and batch processing for large volumes.
    3. Use separate dev, staging and production environments.
    4. Add automatic security checks on the Terraform code and cost reports per client.

Consider security, error handling, observability, testing, CI/CD, and infrastructure hardening.



### 6. Terraform — Adding a Pipeline Step

A new "validate" Lambda needs to be added to the pipeline between Extract and Aggregate. It will validate the extracted fields against a schema before writing results. List every file you'd need to change and what you'd add to each.

**Your answer:**

- Add src/tasks/validate.py with the validation logic, and tests/test_validate.py with its tests.
- Add src/lambdas/validate/handler.py as the entry point. The Dockerfile already copies all of src/, so it does not need to change.
- In terraform/modules/lambda/main.tf, add a log group and a new Lambda function for validate. It uses the same image, with the command set to lambdas.validate.handler.handler.
- In terraform/modules/lambda/outputs.tf, add outputs for the new function's ARN and name.
- In terraform/modules/step-functions/variables.tf, add a variable for the validate Lambda ARN.
- In terraform/modules/step-functions/main.tf, add the new ARN to the role's invoke permission and pass it into the state machine template.
- In terraform/modules/step-functions/state_machine.asl.json, add a Validate step after Extract and point it to Aggregate. Give it a result path and the same retry settings as the other steps.
- In terraform/live/candidate/main.tf, pass the new Lambda ARN from the lambda module to the step functions module.
- In terraform/live/candidate/outputs.tf, add a validate_lambda_name output, and add validate to the loop in the Makefile. Without these, make update-lambdas would skip the new function, which is the same bug I fixed earlier.
- In src/tasks/aggregate.py, include the validation result in the summary.


---

## Solutions Architect Track

*Answer this section only if your email specified Solutions Architect.*

### SA-1. Model Selection & Cost Architecture

This assessment restricts you to Claude Haiku. In a production system processing thousands of documents daily, how would you decide which model to use for classification vs. extraction? What factors (cost, latency, accuracy, token limits) would drive that decision? How would you implement cost attribution per client?

**Your answer:**

### SA-2. Security Review

A client wants to process PHI (protected health information) through this pipeline. What changes are needed to meet HIPAA requirements? Think about data at rest, data in transit, Bedrock's data handling policies, IAM scoping, and logging.

**Your answer:**

### SA-3. Multi-Tenancy

A client wants to offer this pipeline as a SaaS feature where each of their customers uploads documents. How would you isolate tenants? Consider S3 partitioning, IAM scoping, cost attribution, and noisy-neighbor protection.

**Your answer:**

### SA-4. Production Readiness Briefing

List the key points you'd convey to a client's VP of Engineering who approved this project but hasn't seen the implementation. What changes are needed before going to production, and how would you prioritize them?

**Your answer:**

---

## Data Engineer Track

*Answer this section only if your email specified Data Engineer.*

### DE-1. Data Quality & Validation

The pipeline trusts the LLM's JSON output without validation. How would you validate extracted fields against a schema? How would you handle extraction failures — retry, dead-letter queue, or flag for human review? What's your strategy?

**Your answer:**

I would write a schema for each document type with pydantic, which the project already uses, to check required fields, types, date formats and the CVE ID pattern. I would also check that each extracted value actually appears in the source text, which is how I confirmed the "Critical" severity in my own run. If a result fails, the pipeline retries once with the errors added to the prompt, and if it still fails or the confidence is low, it saves the result as "needs review" and sends it to a review queue instead of dropping it. Errors that keep failing after all retries go to a dead-letter queue so they can be run again later.

### DE-2. Pipeline at Scale

This processes one document per Step Functions execution. Design a batch pipeline that handles 100,000 documents per day. What changes to the Step Functions architecture? Where would you parallelize, and where are the bottlenecks?

**Your answer:**

From my runs, each document uses about 2,100 input and 280 output tokens, so 100,000 documents a day is about 210 million input and 28 million output tokens, and the Bedrock quota becomes the main limit. I would put an SQS queue in front of the workflow to absorb bursts, and process documents in batches with a Step Functions Distributed Map, using its concurrency limit to stay under that quota. I would also pass S3 keys between steps instead of the document text, because Step Functions has a 256 KB limit on the data passed between steps. To cut cost, I would use Express workflows, send only the start of each document to Classify, and use Bedrock batch inference for work that is not urgent.


### DE-3. Observability & Data Lineage

How would you monitor this pipeline in production? What metrics, alerts, and dashboards would you build? A downstream team also needs to know which model version and prompt version produced each extraction. How would you track that lineage?

**Your answer:**

I would build a CloudWatch dashboard that shows runs started, succeeded and failed, time per step, Bedrock throttling, token use, confidence scores and the share of "unknown" results. Alarms would go off when failures rise, when the dead-letter queue is not empty, when daily cost passes a budget, or when the share of "unknown" results jumps, since that often means a new kind of document is arriving. For lineage, each result would store the model ID, the prompt version, the schema version, the code version and the source file version, along with the processed time it already has. Keeping these in each result and in a DynamoDB table lets the downstream team find and rerun exactly the documents a prompt change affected.


### DE-4. Caching & Deduplication

If the same document is uploaded twice, the pipeline currently processes it again at full cost. How would you implement caching or deduplication? Consider where in the pipeline to check, what to use as a cache key, and the tradeoffs of different storage options (DynamoDB, S3 metadata, Elasticache).

**Your answer:**

I would check for a duplicate right after Preprocess, before any Bedrock call, because the model calls are where the cost is. The cache key would be a SHA-256 hash of the document content plus the prompt version and model ID, so a renamed copy is still caught and a prompt change starts fresh. I would store it in DynamoDB, because a conditional write checks and saves the key in one step, lookups are fast, and old entries can expire on their own. S3 metadata is cheaper but slower and harder to search, and ElastiCache is the fastest but adds a cluster to run and is more than this volume needs.
