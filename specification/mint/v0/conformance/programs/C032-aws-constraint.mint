mint v0
namespace example.aws
target account {
  kind aws.account
  config {
    account "123456789012"
    region "us-east-1"
  }
}
automation as-aws-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Constrain IAM in the AWS account"
  use aws.iam.constraint v1alpha1
  apply account
  evidence iam.constraint
  require authorization
  forbid mutation
  status draft
}
