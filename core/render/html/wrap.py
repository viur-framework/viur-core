class ListWrapper(list):
    """
        Monkey-Patching for lists.
        Allows collecting sub-properties by using []
        Example: [ {"key":"1"}, {"key":"2"} ]["key"] --> ["1","2"]
    """

    def __init__(self, src):
        """
            Initializes this wrapper by copying the values from src
        """
        super(ListWrapper, self).__init__()
        self.extend(src)

    def __getitem__(self, key):
        if isinstance(key, int):
            return super(ListWrapper, self).__getitem__(key)
        res = []
        for obj in self:
            if isinstance(obj, dict) and key in obj:
                res.append(obj[key])
            elif key in dir(obj):
                res.append(getattr(obj, key))
        return ListWrapper(res)

    def __contains__(self, item):
        if super(ListWrapper, self).__contains__(item):
            return True

        from viur.core.render.html.default import KeyValueWrapper
        for obj in self:
            if isinstance(obj, KeyValueWrapper):
                if str(obj) == item:
                    return True

        return False


class SkelListWrapper(ListWrapper):
    """
        Like ListWrapper, but takes the additional properties
        of skellist into account - namely cursor and customQueryInfo.
    """

    def __init__(self, src, origQuery=None):
        super(SkelListWrapper, self).__init__(src)
        if origQuery is not None:
            self.getCursor = origQuery.getCursor
            self.customQueryInfo = origQuery.customQueryInfo
        else:
            self.getCursor = src.getCursor
            self.customQueryInfo = src.customQueryInfo
