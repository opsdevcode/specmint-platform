mint v0
namespace example.cross
target repo-primary {
  kind repo.github
  config {
    owner "opsdevcode"
    name "specmint"
  }
}
target account {
  kind aws.account
  config {
    account "123456789012"
    region "us-east-1"
  }
}
target project {
  kind gcp.project
  config {
    project "specmint-np"
    region "us-central1"
  }
}
automation as-cross-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Govern repository, AWS, and GCP targets from one intent"
  capabilities repo.branch_protection v1alpha1, aws.iam.constraint v1alpha1, gcp.iam.constraint v1alpha1
  apply repo-primary, account, project
  evidence branch.protection, iam.constraint
  require authorization
  forbid mutation
  status draft
}
