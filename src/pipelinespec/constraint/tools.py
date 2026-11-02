from pipelinespec.models import Clause, JobConstraints, Gate, Scalar, Target, Term, WorkflowTrigger, Unsolved, Variable, kind
from langchain_core.tools import BaseTool, ToolException, tool
from singleton_decorator import singleton
from typing import Any, Literal
from threading import Lock
import json

RECORDED = 'Recorded successfully.'
REJECTED = 'Rejected, nothing recorded:'

@singleton
class ConstraintTools:

    def get(self, constraints: JobConstraints) -> list[BaseTool]:

        lock = Lock()

        @tool(parse_docstring=True)
        def add_gate(name: str, type: Literal['scope', 'branch'], location: str, any_of: list[Clause]) -> str:
            """Records one decision that depends on the run context: whether the job or a step runs, or which path a step's code takes. Record the gates first, then declare the variables they use with add_variable. Replaces a gate of the same name.

            Args:
                name: Short unique name, e.g. step.deploy.if or deploy.sh.upload.
                type: scope for the condition of the job or a step, branch for a decision inside code a step runs.
                location: Where the condition is written, as file:line.
                any_of: The condition as alternatives: the gate holds when any one of the inner lists holds, and an inner list holds when all of its terms do. A term is {"name": ..., "op": ..., "value": ...}: the name of a variable (declared afterwards with add_variable) or the built-in event, an operator (==, !=, <, <=, >, >=, starts_with, ends_with, contains) and a value of the variable's type. Negation goes in the term, with != or by comparing a boolean with false. For a && (b || c), write two lists: [a, b] and [a, c].
            """

            with lock:
                gate = Gate(name=name, type=type, location=location, any_of=any_of)
                error = self.__invalid(constraints, gate)

                if error:
                    self.__reject(error)

                self.__put(constraints.gates, gate)
                missing = self.pending(constraints).get(name)

                if missing:
                    return f'{RECORDED} Declare a variable with add_variable for: {", ".join(missing)}.'

                return RECORDED

        @tool(parse_docstring=True)
        def add_variable(name: str, target: Target, values: list[Scalar]) -> str:
            """Declares one input that gates refer to by name: where its value lives in the run context and the values worth testing. Declare it once, after the first gate that uses it; every gate that uses the name shares it. Replaces a variable of the same name.

            Args:
                name: The name a gate uses for it, e.g. locked. A gate may also write the target or any dotted end of it (payload.issue.locked, issue.locked).
                target: Where the value lives: actor, or payload.<dotted path>, e.g. payload.issue.locked.
                values: The values worth testing, all of one type (strings, true/false or numbers). The most ordinary one first, then one that flips a condition, e.g. [false, true].
            """

            with lock:
                variable = Variable(target=target, values=values)
                self.__check_types(constraints, name, variable)

                if constraints.variables.get(name) == variable:
                    self.__reject(f'"{name}" is already declared exactly like this. Nothing changed: declare the variables that are still missing, or stop if none are.')

                trial = constraints.model_copy(update={'variables': {**constraints.variables, name: variable}})

                if not any(trial.aliases.get(word) == name for gate in trial.gates for word in self.__words(gate)):
                    self.__reject(f'No recorded gate uses the name "{name}". Record the gate that uses it with add_gate first, then declare its variable.')

                for gate in trial.gates:
                    error = self.__invalid(trial, gate)

                    if error:
                        self.__reject(f'With this variable, gate "{gate.name}" is not valid: {error}')

                constraints.variables[name] = variable

                if constraints.constants.pop(variable.target, None) is not None:
                    return f'{RECORDED} It replaced the constant for {variable.target}, which a gate now compares.'

                return RECORDED

        @tool(parse_docstring=True)
        def add_unsolved(name: str, reason: str, location: str) -> str:
            """Records one decision on something the run context does not set. It is recorded, but not tested. Replaces an entry of the same name.

            Args:
                name: Short unique name, e.g. step.deploy.success.
                reason: What it depends on that the run context does not set.
                location: Where it is written, as file:line.
            """

            with lock:
                self.__put(constraints.unsolved, Unsolved(name=name, reason=reason, location=location))

                return RECORDED

        @tool(parse_docstring=True)
        def add_constant(target: Target, value: Scalar) -> str:
            """Records a fixed value the job needs but no condition depends on, like an argument, path or message.

            Args:
                target: Where the value goes, written like a variable's target, e.g. payload.pull_request.base.sha.
                value: A string, a boolean or an integer.
            """

            with lock:
                if target in {variable.target for variable in constraints.variables.values()}:
                    self.__reject(f'"{target}" is a variable of the gates, so its values come from there. It cannot also be a constant.')

                if target in constraints.constants and constraints.constants[target] == value:
                    self.__reject(f'"{target}" is already recorded with this value. Nothing changed: move on to what is not recorded yet.')

                constraints.constants[target] = value

                return RECORDED

        @tool(parse_docstring=True)
        def recorded() -> str:
            """Show everything recorded so far."""

            return constraints.model_dump_json(indent=2)

        recording = [add_gate, add_variable, add_unsolved, add_constant]

        for recorder in recording:
            recorder.handle_tool_error = True

        return [*recording, recorded]

    def triggers(self, found: list[WorkflowTrigger]) -> list[BaseTool]:

        lock = Lock()

        @tool(parse_docstring=True)
        def add_trigger(event: str, payload: dict[str, Any] | None = None) -> str:
            """Records one example of the workflow being started: an event and a payload that satisfies the workflow's conditions on that event. Replaces the example for the same event.

            Args:
                event: The event name, as the workflow lists it.
                payload: Only the fields the workflow's conditions on this event read, nested as in the event's real payload, with values that satisfy them. Leave it out when the event has no conditions.
            """

            with lock:
                trigger = WorkflowTrigger(event=event, payload=payload or {})
                index = next((index for index, existing in enumerate(found) if existing.event == event), None)

                if index is None:
                    found.append(trigger)
                    return RECORDED

                if found[index] == trigger:
                    self.__reject(f'The example for "{event}" is already recorded exactly like this. Nothing changed: move on to an event that has none yet, or stop if every event has one.')

                found[index] = trigger

                return f'{RECORDED} It replaced the earlier example for "{event}".'

        @tool(parse_docstring=True)
        def recorded() -> str:
            """Show the examples recorded so far."""

            return json.dumps([trigger.model_dump(mode='json') for trigger in found], indent=2)

        add_trigger.handle_tool_error = True

        return [add_trigger, recorded]

    def pending(self, constraints: JobConstraints) -> dict[str, list[str]]:

        aliases = constraints.aliases
        found = {gate.name: sorted(word for word in self.__words(gate) if word not in aliases) for gate in constraints.gates}

        return {name: words for name, words in found.items() if words}

    def __words(self, gate: Gate) -> set[str]:

        return {term.name for clause in gate.any_of for term in clause} - {'event'}

    def __invalid(self, constraints: JobConstraints, gate: Gate) -> str | None:

        aliases = constraints.aliases

        for term in (term for clause in gate.any_of for term in clause):
            if term.name == 'event':
                problem = self.__mismatch(term, 'str')
            elif term.name in aliases:
                problem = self.__mismatch(term, constraints.variables[aliases[term.name]].kind)
            else:
                continue

            if problem:
                return problem

        return None

    def __mismatch(self, term: Term, held: str) -> str | None:

        if term.op in ('<', '<=', '>', '>=') and held != 'int':
            return f'{term.op} compares numbers, but "{term.name}" holds {held} values.'

        if term.op in ('starts_with', 'ends_with', 'contains') and held != 'str':
            return f'{term.op} works on strings, but "{term.name}" holds {held} values.'

        if kind(term.value) != held:
            example = {'bool': 'true or false', 'int': 'a number such as 1', 'str': 'a quoted string such as "main"'}[held]
            return f'"{term.name}" holds {held} values, but it is compared with {term.value!r}, a {kind(term.value)}. Compare it with {example}.'

        return None

    def __check_types(self, constraints: JobConstraints, name: str, variable: Variable) -> None:

        known = {'event': 'str', **{existing.target: existing.kind for key, existing in constraints.variables.items() if key != name}}
        expected = known.get(variable.target, variable.kind)

        if variable.kind != expected:
            example = {'bool': '[false, true]', 'int': '[1, 2]', 'str': '["main", "dev"]'}[expected]
            self.__reject(f'"{name}" ({variable.target}) has {variable.kind} values {list(variable.values)}, but {variable.target} holds a {expected} (as the other variables use it). Give values like {example}.')

    def __put[Item: Gate | Unsolved](self, items: list[Item], item: Item) -> None:

        for index, existing in enumerate(items):
            if existing.name != item.name:
                continue

            if existing == item:
                self.__reject(f'"{item.name}" is already recorded exactly like this. Nothing changed: move on to what is not recorded yet, or stop if everything is.')

            items[index] = item
            return

        items.append(item)

    def __reject(self, reason: str) -> None:

        raise ToolException(f'{REJECTED} {reason}')

constraint_tools = ConstraintTools()
