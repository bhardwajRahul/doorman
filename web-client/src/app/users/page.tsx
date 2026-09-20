'use client'
import { TableSkeleton } from '@/components/TableSkeleton'
import toast from 'react-hot-toast'

import React, { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Layout from '@/components/Layout'
import Pagination from '@/components/Pagination'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { SERVER_URL } from '@/utils/config'
import {
  SignalEmptyState,
  SignalPageHeader,
  SignalPanel,
  SignalPrimaryLink,
  SignalRecordIcon,
  SignalSearchInput,
  SignalTable
} from '@/components/signal/Signal'

interface User {
  username: string
  email: string
  active: boolean
  created_at: string
  last_login?: string
  roles?: string[]
}

const UsersPage = () => {
  const router = useRouter()
  const [users, setUsers] = useState<User[]>([])
  const [allUsers, setAllUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [sortBy, setSortBy] = useState('username')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [hasNext, setHasNext] = useState(false)

  useEffect(() => {
    fetchUsers()
  }, [page, pageSize])

  const fetchUsers = async () => {
    try {
      setLoading(true)
      const { fetchJson } = await import('@/utils/http')
      const data: any = await fetchJson(`${SERVER_URL}/platform/user/all?page=${page}&page_size=${pageSize}`)
      const userList = Array.isArray(data) ? data : (data.users || data.response?.users || [])
      setAllUsers(userList)
      setUsers(userList)
      const hn = (data?.has_next ?? data?.response?.has_next)
      setHasNext(typeof hn === 'boolean' ? hn : (userList || []).length === pageSize)
    } catch (err) {

      toast.error('Failed to load users. Please try again later.')
      setUsers([])
      setAllUsers([])
      setHasNext(false)
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (!searchTerm.trim()) {
      setUsers(allUsers)
      return
    }

    const filteredUsers = allUsers.filter(user =>
      user.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
      user.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (user.roles || []).some(role => role.toLowerCase().includes(searchTerm.toLowerCase()))
    )
    setUsers(filteredUsers)
  }

  const handleSort = (sortField: string) => {
    const isSameField = sortField === sortBy
    const newOrder = isSameField ? (sortOrder === 'asc' ? 'desc' : 'asc') : 'asc'
    setSortBy(sortField)
    setSortOrder(newOrder)
    const sortedUsers = [...users].sort((a, b) => {
      let comparison = 0
      if (sortField === 'username') {
        comparison = a.username.localeCompare(b.username)
      } else if (sortField === 'email') {
        comparison = a.email.localeCompare(b.email)
      } else if (sortField === 'status') {
        comparison = a.active === b.active ? 0 : a.active ? -1 : 1
      }
      return newOrder === 'asc' ? comparison : -comparison
    })
    setUsers(sortedUsers)
  }

  const handleUserClick = (user: User) => {
    sessionStorage.setItem('selectedUser', JSON.stringify(user))
    router.push(`/users/${user.username}`)
  }

  const formatDate = (dateString: string) => {
    if (!dateString) return 'Never'
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    })
  }

  return (
    <ProtectedRoute requiredPermission="manage_users">
      <Layout>
      <div className="space-y-6">
        <SignalPageHeader
          kicker="Identity & Access"
          title={<>User Accounts.</>}
          description="Manage user authentication, role assignments, and gateway permissions."
          actions={
            <SignalPrimaryLink href="/users/add">
              Add User
            </SignalPrimaryLink>
          }
        />

        <SignalPanel tone="white" title="Search and Filters" kicker={`User Directory (Showing ${users.length} of ${allUsers.length})`}>
          <div className="flex flex-col sm:flex-row gap-4">
            <form onSubmit={handleSearch} className="flex-1">
              <SignalSearchInput
                value={searchTerm}
                onChange={(val) => {
                  setSearchTerm(val)
                  if (!val) setUsers(allUsers)
                }}
                onClear={() => setUsers(allUsers)}
                placeholder="Search users by username, email, or role..."
              />
            </form>
          </div>
        </SignalPanel>

        {loading ? (
          <TableSkeleton />
        ) : (
          /* Users Table */
          <SignalPanel tone="white" title="Registered Users" kicker={`Active Directory (${users.length})`}>
            <SignalTable>
              <thead>
                <tr>
                  <th onClick={() => handleSort('username')} className="cursor-pointer hover:bg-gray-800 transition-colors">
                    <div className="flex items-center gap-1">Username {sortBy === 'username' && (sortOrder === 'asc' ? '▲' : '▼')}</div>
                  </th>
                  <th onClick={() => handleSort('email')} className="cursor-pointer hover:bg-gray-800 transition-colors">
                    <div className="flex items-center gap-1">Email {sortBy === 'email' && (sortOrder === 'asc' ? '▲' : '▼')}</div>
                  </th>
                  <th>Roles</th>
                  <th onClick={() => handleSort('status')} className="cursor-pointer hover:bg-gray-800 transition-colors">
                    <div className="flex items-center gap-1">Status {sortBy === 'status' && (sortOrder === 'asc' ? '▲' : '▼')}</div>
                  </th>
                  <th>Last Login</th>
                  <th className="w-12"></th>
                </tr>
              </thead>
              <tbody>
                  {users.map((user) => (
                    <tr
                      key={user.username}
                      onClick={() => handleUserClick(user)}
                      className="cursor-pointer hover:bg-gray-50 dark:hover:bg-dark-surfaceHover transition-colors"
                    >
                      <td>
                        <div className="flex items-center">
                          <SignalRecordIcon kind="user" />
                          <div className="ml-3">
                            <p className="font-medium text-gray-900 dark:text-white">
                              {user.username}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td>
                        <p className="text-sm text-gray-900 dark:text-white">{user.email}</p>
                      </td>
                      <td>
                        <div className="flex flex-wrap gap-1">
                          {(user.roles || []).slice(0, 2).map((role, index) => (
                            <span key={index} className="badge badge-primary text-xs">
                              {role}
                            </span>
                          ))}
                          {(user.roles || []).length > 2 && (
                            <span className="badge badge-gray text-xs">
                              +{(user.roles || []).length - 2}
                            </span>
                          )}
                        </div>
                      </td>
                      <td>
                        <span className={`badge ${user.active ? 'badge-success' : 'badge-error'}`}>
                          {user.active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td>
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          {formatDate(user.last_login || '')}
                        </p>
                      </td>
                      <td>
                        <button className="btn btn-ghost btn-sm">
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </SignalTable>

              <Pagination
                page={page}
                pageSize={pageSize}
                onPageChange={setPage}
                onPageSizeChange={(s) => { setPageSize(s); setPage(1) }}
                hasNext={hasNext}
              />

              {users.length === 0 && !loading && (
                <SignalEmptyState
                  title="No Users Found"
                  action={
                    <SignalPrimaryLink href="/users/add">
                      Add User
                    </SignalPrimaryLink>
                  }
                >
                  {searchTerm ? 'Try adjusting your search terms.' : 'Get started by creating your first user account.'}
                </SignalEmptyState>
              )}
            </SignalPanel>
          )}
      </div>
    </Layout>
  </ProtectedRoute>
  )
}

export default UsersPage
