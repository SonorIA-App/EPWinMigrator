## HOTFIX — Correção Crítica

> **Atenção:** este PR deve ser aberto de `hotfix/*` diretamente para `main` e,
> após o merge, deve ser portado imediatamente para `staging` e `develop`.

## Problema crítico
<!-- O que está falhando? Ex: corrupção de dados durante migração, erro fatal em produção -->


## Causa identificada


## Solução aplicada


## Avaliação de risco
- [ ] A correção não altera dados já migrados corretamente
- [ ] Testado com banco de dados real antes deste PR
- [ ] Existe plano de rollback

## Plano de rollback
<!-- Como desfazer a migração problemática se necessário? -->


## Checklist
- [ ] Lint passou (`ruff check .`)
- [ ] Testes passam (`pytest`)
- [ ] Sem credenciais ou dados de pacientes no código
- [ ] Testado com `EPWinData.mdb` e `BLPatients.mdb` reais

### Pós-merge obrigatório
- [ ] Portado para `staging` via PR
- [ ] Portado para `develop` via PR
- [ ] Incidente documentado

## Issues relacionadas
Closes #
