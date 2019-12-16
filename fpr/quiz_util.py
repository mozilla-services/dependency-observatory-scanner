import functools
from typing import AbstractSet, Dict, Sequence, Optional, Callable, Tuple, Union

import quiz


_ = quiz.SELECTOR

SelectionPathElement = Union[int, str]
SelectionPath = Sequence[SelectionPathElement]
SelectionKwargsValue = Union[
    int, str
]  # we currently set first / last ints for page size, before / after strs, and repo owner and name strs
SelectionKwargs = Dict[str, SelectionKwargsValue]
SelectionUpdate = Tuple[SelectionPath, SelectionKwargs]


class QuizSelectionNotFound(ValueError):
    pass


def get(
    selection_set: quiz.SelectionSet, path_item: SelectionPathElement
) -> quiz.Field:
    for field in selection_set:
        if isinstance(path_item, int):
            fields = list(selection_set)
            if path_item < len(fields):
                return fields[path_item]
        elif isinstance(path_item, str):
            if isinstance(field, str) and field == path_item:
                return field
            elif isinstance(field, quiz.build.Field) and field.name == path_item:
                return field
    return None


def get_in(selection: quiz.Selection, path: SelectionPath) -> Optional[quiz.Selection]:
    if not len(path):
        return selection
    subselection = selection
    while True:
        field = get(subselection, path[0])
        if field is None:
            return None
        if len(path) == 1:
            return subselection
        else:
            subselection = field.selection_set
            path = path[1:]


def get_kwargs_in(
    selection: quiz.Selection, path: SelectionPath
) -> Optional[SelectionKwargs]:
    if not len(path):
        return None

    subselection = selection
    while True:
        field = get(subselection, path[0])
        if field is None:
            return None
        if len(path) == 1:
            return field.kwargs
        else:
            subselection = field.selection_set
            path = path[1:]


def update_in(
    selection: quiz.Selection,
    path: SelectionPath,
    updater: Callable[[quiz.Selection], quiz.Selection],
) -> quiz.Selection:
    """runs the param updater function on the value at a nested key

    (specified by param path as a string of Field names) in a quiz.Selection and
    returns a new Selection e.g.

    To remove quiz Fields apply updater to field one layer up:
    """
    subselection = get_in(selection, path)
    if subselection is None:
        raise QuizSelectionNotFound(f"Failed to find {path} in a quiz.selection")

    updated_subselection = updater(subselection)

    # consume path to update parents and rebuild the complete selection
    while True:
        if len(path) <= 1:
            updated_selection = updated_subselection
            break

        parent_sel = get_in(selection, path[:-1])
        if parent_sel is None:
            raise QuizSelectionNotFound(
                f"Failed to find parent selection in a quiz.selection"
            )

        fields = []
        for i, field in enumerate(parent_sel):
            if field.name == path[-2] or i == path[-2]:
                fields.append(field.replace(selection_set=updated_subselection))
            else:
                fields.append(field)

        updated_selection = quiz.SelectionSet._make(fields)

        path = path[:-1]
        updated_subselection = updated_selection

    return updated_selection


def upsert_kwargs(
    field_name: str, kwargs: SelectionKwargs, selection: quiz.Selection
) -> quiz.Selection:
    fields = [
        field.replace(
            kwargs={**field.kwargs, **kwargs}, selection_set=field.selection_set
        )
        if field.name == field_name
        else field
        for field in selection
    ]
    return quiz.SelectionSet._make(fields)


def multi_upsert_kwargs(
    updates: Sequence[SelectionUpdate], selection: quiz.Selection
) -> quiz.Selection:
    for path, new_kwargs in updates:
        selection = update_in(
            selection, path, functools.partial(upsert_kwargs, path[-1], new_kwargs)
        )
    return selection


def raw_result_to_dict(result: Optional[quiz.execution.RawResult]) -> Dict:
    """drop __metadata__ from a quiz.execution.RawResult so it pickles
    without hitting the recursion limit"""
    assert result
    assert isinstance(result, dict)
    return {k: v for k, v in result.items() if k != "__metadata__"}
