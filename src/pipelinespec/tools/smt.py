from z3 import And, Bool, BoolVal, Contains, Int, IntVal, Not, Optimize, Or, PrefixOf, Solver, String, StringVal, SuffixOf, Xor, is_true, sat, unsat
from pipelinespec.models import Gate, JobConstraints, Scalar, Term, Variant, WorkflowTrigger, kind
from singleton_decorator import singleton
from pipelinespec import log, settings
from itertools import product
import operator

COMPARE = {'==': operator.eq, '!=': operator.ne, '<': operator.lt, '<=': operator.le, '>': operator.gt, '>=': operator.ge}

@singleton
class Smt:

    def solve(self, constraints: JobConstraints, workflow_triggers: list[WorkflowTrigger]) -> list[Variant]:

        if not workflow_triggers:
            raise ValueError('There is no event to solve for: the workflow pass recorded no trigger.')

        events = [trigger.event for trigger in workflow_triggers]

        # Formatting

        domains = {
            'event': events,
            **{target: values for target, values in constraints.domains.items() if values}
        }

        kinds = {
            target: kind(values[0])
            for target, values in domains.items()
        }

        symbols = {
            target: {
                'bool': Bool,
                'int': Int,
                'str': String
            }[kinds[target]](target)
            for target in domains
        }

        domain = [
            self.__any([symbols[target] == self.__literal(value) for value in values])
            for target, values in domains.items()
        ]

        preferred = [symbols[target] == self.__literal(values[0]) for target, values in domains.items()]
        
        expressions = {gate.name: self.__gate(gate, constraints, symbols) for gate in constraints.gates}

        formulas = Solver()
        formulas.add(*domain, *[Bool(name) == expression for name, expression in expressions.items()])
        (settings.file.output / 'solver.smt2').write_text(formulas.sexpr())

        goals = [('all conditions hold', self.__all(list(expressions.values())) if expressions else BoolVal(True))]
        for name, expression in expressions.items():
            goals += [(f'{name} holds', expression), (f'{name} fails', Not(expression))]

        candidates: dict[tuple, Variant] = {}

        for event, (reason, goal) in product(events, goals):
            optimizer = Optimize()
            optimizer.add(*domain, symbols['event'] == StringVal(event), goal)

            for preference in preferred:
                optimizer.add_soft(preference)

            if optimizer.check() != sat:
                if settings.verbose:
                    log(f'No {event} context satisfies: {reason}.')

                continue

            model = optimizer.model()
            assignment = {target: self.__value(kinds[target], model.eval(symbol, model_completion=True)) for target, symbol in symbols.items()}
            candidates.setdefault(tuple(sorted(assignment.items())), Variant(reason=f'{event}: {reason}', assignment=assignment))

        return list(candidates.values())

    def equivalent(self, left: JobConstraints, left_gates: list[Gate], right: JobConstraints, right_gates: list[Gate], events: list[str]) -> bool:

        kinds: dict[str, str] = {}

        for constraints in (left, right):
            for variable in constraints.variables.values():
                if kinds.setdefault(variable.target, variable.kind) != variable.kind:
                    return False

        symbols = {'event': String('event'), **{target: {'bool': Bool, 'int': Int, 'str': String}[name](target) for target, name in kinds.items()}}
        allowed = self.__any([symbols['event'] == StringVal(event) for event in events]) if events else BoolVal(True)
        conjunction = lambda constraints, gates: self.__all([self.__gate(gate, constraints, symbols) for gate in gates]) if gates else BoolVal(True)

        solver = Solver()
        solver.add(allowed, Xor(conjunction(left, left_gates), conjunction(right, right_gates)))

        return solver.check() == unsat

    def __gate(self, gate: Gate, constraints: JobConstraints, symbols: dict):

        aliases = constraints.aliases
        names = {'event': symbols['event'], **{name: symbols[variable.target] for name, variable in constraints.variables.items()}}

        def term(item: Term):

            name = aliases.get(item.name, item.name)

            if name not in names:
                raise ValueError(f'"{item.name}" has no variable. Declared variables: {", ".join(repr(key) for key in constraints.variables) or "none"}. Declare it with add_variable, or record the condition with add_unsolved if the run context cannot set it.')

            return self.__term(item, names[name])

        return self.__any([self.__all([term(item) for item in clause]) for clause in gate.any_of])

    def __term(self, term: Term, symbol):

        value = self.__literal(term.value)

        match term.op:
            case 'starts_with':
                return PrefixOf(value, symbol)
            case 'ends_with':
                return SuffixOf(value, symbol)
            case 'contains':
                return Contains(symbol, value)

        return COMPARE[term.op](symbol, value)

    def __all(self, items: list):

        return items[0] if len(items) == 1 else And(*items)

    def __any(self, items: list):

        return items[0] if len(items) == 1 else Or(*items)

    def __literal(self, value: Scalar):

        if isinstance(value, bool):
            return BoolVal(value)

        return IntVal(value) if isinstance(value, int) else StringVal(value)

    def __value(self, kind: str, value) -> Scalar:

        if kind == 'bool':
            return is_true(value)

        return value.as_long() if kind == 'int' else value.as_string()

smt = Smt()
