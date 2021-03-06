local kap = import 'lib/kapitan.libjsonnet';
local inv = kap.inventory();
local params = inv.parameters.{{ cookiecutter.parameter_key }};
local argocd = import 'lib/argocd.libjsonnet';

local app = argocd.App('{{ cookiecutter.slug }}', params.namespace);

{
  '{{ cookiecutter.slug }}': app,
}
