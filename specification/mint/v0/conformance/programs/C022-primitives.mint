mint v0
namespace example.types
const retries 3
const enabled true
const label "prod"

automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Ensure a sandbox marker exists after an authorized plan"
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  evidence marker.present
  require authorization
  forbid mutation
  status draft
}
