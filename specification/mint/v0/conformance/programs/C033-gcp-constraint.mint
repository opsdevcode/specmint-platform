mint v0
namespace example.gcp
target project {
  kind gcp.project
  config {
    project "specmint-np"
    region "us-central1"
  }
}
automation as-gcp-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Constrain IAM in the GCP project"
  use gcp.iam.constraint v1alpha1
  apply project
  evidence iam.constraint
  require authorization
  forbid mutation
  status draft
}
