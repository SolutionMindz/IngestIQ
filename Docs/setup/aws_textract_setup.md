# AWS Textract setup

The backend uses **AWS Textract** for PDF extraction when credentials are configured. Settings are read from environment variables (e.g. `backend/.env`).

---

## 1. Settings (environment variables)

The app reads these from `backend/.env` (or the environment). They are defined in [backend/app/config.py](../backend/app/config.py):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_ACCESS_KEY_ID` | Yes (for Textract) | — | AWS access key ID |
| `AWS_SECRET_ACCESS_KEY` | Yes (for Textract) | — | AWS secret access key |
| `AWS_SESSION_TOKEN` | Yes for temporary creds | — | Session token when using temporary/federated credentials (e.g. `aws login`, federation token) |
| `AWS_REGION` | No | `us-east-1` | AWS region where Textract is used |

If `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` is missing, the backend still runs but uses a **placeholder** for the Textract side (no real AWS calls). When using **temporary credentials** (access key ID starts with `ASIA...`), you must also set `AWS_SESSION_TOKEN`.

---

## 2. Configure via `.env`

1. Copy the example env file:

   ```bash
   cd backend
   cp .env.example .env
   ```

2. Edit `backend/.env` and set:

   ```env
   AWS_ACCESS_KEY_ID=AKIA...
   AWS_SECRET_ACCESS_KEY=...
   AWS_REGION=us-east-1
   ```

3. Restart the backend so it picks up the new values.

---

## 3. Getting AWS credentials

1. Log in to the [AWS Console](https://console.aws.amazon.com/).
2. Open **IAM** → **Users** → your user (or create one) → **Security credentials**.
3. Under **Access keys**, create a new access key.
4. Copy the **Access key ID** and **Secret access key** into `.env` as above.
5. Ensure the IAM user has a policy that allows Textract, for example:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "textract:AnalyzeDocument",
           "textract:DetectDocumentText"
         ],
         "Resource": "*"
       }
     ]
   }
   ```

---

## 4. Region

- Textract is available in [several regions](https://docs.aws.amazon.com/textract/latest/dg/regions.html). Use one that supports Textract (e.g. `us-east-1`, `us-east-2`, `eu-west-1`).
- Set `AWS_REGION` in `.env` to that region (e.g. `us-east-1`).

---

## 5. How the backend uses these settings

- [backend/app/config.py](../backend/app/config.py) defines `Settings` with `aws_access_key_id`, `aws_secret_access_key`, and `aws_region` (loaded from `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`).
- [backend/app/services/pdf_extractor.py](../backend/app/services/pdf_extractor.py) calls `get_settings()`. If both key and secret are set, it uses `boto3.client("textract", region_name=settings.aws_region)` and sends the PDF with `AnalyzeDocument` (TABLES, FORMS). If not set, it creates a mock extraction and does not call AWS.

---

## 6. Input quality (DPI, format)

Textract accuracy depends on input quality. The pipeline is set up to follow best practices:

| Recommendation | How the project handles it |
|----------------|-----------------------------|
| **Minimum 300 DPI** (400 for code-heavy pages) | Screenshots and PDF→image rendering use **300 DPI by default**, configurable via `SCREENSHOT_DPI` in `.env`. Set `SCREENSHOT_DPI=400` for code-heavy technical books. |
| **Avoid JPEG; use PNG** | All images sent to Textract are **PNG** (screenshots saved as `.png`, sync multipage uses `pix.tobytes(output="png")`). |
| **Do not resize before sending** | Images are sent at the rendered resolution (no downscaling). |
| **Preserve original PDF when possible** | Single-page PDFs are sent as raw PDF bytes. Multi-page with `AWS_S3_BUCKET` set uses the original PDF in S3. When rendering from PDF (no S3, or no screenshots), the same configurable DPI is used. |

For code-heavy technical books, set `SCREENSHOT_DPI=400` in `backend/.env` and re-run extraction so new screenshots and Textract input use 400 DPI.

---

## 7. Troubleshooting

### "The security token included in the request is invalid" (UnrecognizedClientException)

AWS is rejecting your credentials. Check:

1. **No extra spaces or newlines** in `backend/.env`. Use one line per variable:
   ```env
   AWS_ACCESS_KEY_ID=AKIA...
   AWS_SECRET_ACCESS_KEY=your_secret_here
   AWS_REGION=us-east-1
   ```
   Do not put a space after `=`. Do not wrap values in quotes unless the value contains spaces (and then use one pair only).

2. **Keys are valid.** In IAM, access keys can be deactivated or deleted. Create a **new access key** and update `.env`.

3. **Verify with AWS CLI** (if installed):
   ```bash
   export $(grep -v '^#' backend/.env | xargs)
   aws sts get-caller-identity
   ```
   If that fails, the credentials are wrong or inactive.

---

## 8. Security

- **Do not** commit `.env` (it should be in `.gitignore`). Only commit `.env.example` with placeholder names.
- Prefer IAM roles (e.g. on EC2/ECS/Lambda) over long‑lived access keys when running in AWS.
- Restrict the IAM policy to the minimum needed (e.g. only Textract and, if used, S3 for input).
